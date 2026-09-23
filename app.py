# -*- coding: utf-8 -*-
"""
app.py
======
[HW10 Taiwan Weather Forecast Web Application]
Integrates Tasks 1–5, Stage 1 (Live Data Update & Freshness Check), and Stage 2 (Basic Weather Info).
Stage 3-A: Taiwan map promoted to main visual element; compact single-row header.

Features:
- Pure SQLite data connection: connects to data.db and queries TemperatureForecasts.
- Centralized weather update workflow (via weather_service.py).
- Automatic freshness check on app startup (default 6h refresh interval).
- Manual "更新天氣資料" button with transaction safety & non-blocking fallback on CWA API downtime.
- Asia/Taipei timezone display for data fetch timestamp, clearly distinct from forecast dates.
- Preserves 1-decimal-place temperature precision, 6 regions, and 7-day forecast.
- Extended with Stage 2 basic weather information: Weather phenomenon (天氣現象) & PoP (降雨機率).
- Stage 3-A: Map is now the hero element at the top of the page; chart/table moved below.
"""

from datetime import datetime, timezone, timedelta
try:
    from zoneinfo import ZoneInfo
    TAIPEI_TZ = ZoneInfo("Asia/Taipei")
except Exception:
    TAIPEI_TZ = timezone(timedelta(hours=8))

import json
import os
import sqlite3
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import folium
from folium import DivIcon
from streamlit_folium import st_folium

import database
import weather_service

# =============================================================
# 專案路徑與分區設定
# =============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data.db")

REGION_COORDINATES = {
    "北部地區": [25.04, 121.56],
    "中部地區": [24.15, 120.67],
    "南部地區": [22.99, 120.21],
    "東北部地區": [24.75, 121.75],
    "東部地區": [23.98, 121.60],
    "東南部地區": [22.76, 121.14],
}

REGION_SHORT_NAMES = {
    "北部地區": "北部",
    "中部地區": "中部",
    "南部地區": "南部",
    "東北部地區": "東北部",
    "東部地區": "東部",
    "東南部地區": "東南部",
}

GEOJSON_PATH = os.path.join(BASE_DIR, "taiwan_regions.geojson")

REGION_BOUNDARY_COLORS = {
    "北部地區": "#2563EB",   # 湛藍
    "中部地區": "#059669",   # 翡翠綠
    "南部地區": "#D97706",   # 暖琥珀
    "東北部地區": "#7C3AED", # 紫羅蘭
    "東部地區": "#0891B2",   # 青碧藍
    "東南部地區": "#DB2777", # 玫紅
}


@st.cache_data
def load_region_boundaries():
    """載入六大氣象分區 GeoJSON 邊界資料（快取以提升呈現效能）。"""
    if not os.path.exists(GEOJSON_PATH):
        return {}
    with open(GEOJSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    grouped = {r: [] for r in REGION_BOUNDARY_COLORS}
    for feature in data.get("features", []):
        r = feature.get("properties", {}).get("region")
        if r in grouped:
            grouped[r].append(feature)
    return grouped


# =============================================================
# 資料庫查詢函數 (純 SQLite，絕不於展示層直接呼叫 API)
# =============================================================
def get_connection(db_path=DB_PATH):
    """建立 SQLite 資料庫連線。"""
    if not os.path.exists(db_path):
        return None
    return sqlite3.connect(db_path)


def get_available_regions(conn):
    """從 SQLite 資料庫查詢所有不重複的地區名稱。"""
    query = "SELECT DISTINCT regionName FROM TemperatureForecasts ORDER BY id;"
    df = pd.read_sql_query(query, conn)
    return df["regionName"].tolist()


def get_region_forecast(conn, region_name):
    """依選定地區從 SQLite 查詢氣溫與天氣預報資料。"""
    query = """
    SELECT dataDate AS Date, mint AS MinT, maxt AS MaxT, weather, pop
    FROM TemperatureForecasts
    WHERE regionName = ?
    ORDER BY dataDate ASC;
    """
    df = pd.read_sql_query(query, conn, params=(region_name,))
    return df


def get_available_dates(conn):
    """從 SQLite 資料庫查詢所有可供選擇的預報日期。"""
    query = "SELECT DISTINCT dataDate FROM TemperatureForecasts ORDER BY dataDate ASC;"
    df = pd.read_sql_query(query, conn)
    return df["dataDate"].tolist()


def get_forecast_by_date(conn, selected_date):
    """依選定日期從 SQLite 查詢六大區域的天氣預報資料。"""
    query = """
    SELECT regionName, mint, maxt, weather, pop
    FROM TemperatureForecasts
    WHERE dataDate = ?;
    """
    df = pd.read_sql_query(query, conn, params=(selected_date,))
    return df


# =============================================================
# 輔助函式：氣溫分級色彩對應
# =============================================================
def get_temperature_color(avg_temp):
    """
    依據平均氣溫設定標記色彩（符合作業 Task 5 規範）：
    - Below 20°C: blue
    - 20°C to below 25°C: green
    - 25°C to below 30°C: orange
    - 30°C and above: red
    """
    if avg_temp < 20.0:
        return "blue", "#2E86AB", "< 20°C (藍色 - 偏涼)"
    elif avg_temp < 25.0:
        return "green", "#48A9A6", "20 - 25°C (綠色 - 舒適)"
    elif avg_temp < 30.0:
        return "orange", "#F4D35E", "25 - 30°C (橘黃色 - 偏熱)"
    else:
        return "red", "#EE6055", "≥ 30°C (紅色 - 炎熱)"


# =============================================================
# Streamlit 頁面主程式
# =============================================================
def main():
    # ── 頁面配置（wide 版面）──────────────────────────────────────────
    st.set_page_config(
        page_title="Taiwan Weather Forecast Dashboard",
        page_icon="⛅",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    # ── 主題狀態管理 ──────────────────────────────────────────
    if "theme" not in st.session_state:
        st.session_state["theme"] = "light"
    is_dark = (st.session_state.get("theme") == "dark")

    # ── CSS 樣式：最小化外邊距，支援深色 / 淺色主題 ──
    dark_css = ""
    if is_dark:
        dark_css = """
        .stApp {
            background-color: #0f172a !important;
            color: #f1f5f9 !important;
        }
        .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6, .stApp p, .stApp label, .stApp div {
            color: #f1f5f9;
        }
        .stCaption, [data-testid="stCaptionContainer"] {
            color: #94a3b8 !important;
        }
        div[data-baseweb="select"] > div {
            background-color: #1e293b !important;
            color: #f1f5f9 !important;
            border-color: #334155 !important;
        }
        button[kind="secondary"] {
            background-color: #1e293b !important;
            color: #f1f5f9 !important;
            border-color: #334155 !important;
        }
        div[data-testid="stExpander"] {
            background-color: #1e293b !important;
            border-color: #334155 !important;
        }
        """

    st.markdown(
        f"""
        <style>
        /* 縮減 Streamlit 預設過大的頂部與兩側邊距 */
        .block-container {{
            padding-top: 1rem !important;
            padding-bottom: 0.5rem !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
            max-width: 100% !important;
        }}
        /* 緊湊頂部系統標題列留白 */
        header[data-testid="stHeader"] {{
            height: 1.5rem !important;
            background: transparent !important;
        }}
        {dark_css}
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ── 啟動時自動檢查資料新鮮度 ─────────────────────────────────────
    if "freshness_checked" not in st.session_state:
        st.session_state["freshness_checked"] = True
        status = weather_service.get_sync_status()
        if status["is_stale"]:
            with st.spinner("🔄 資料庫資料已逾期，正在自中央氣象署同步最新預報..."):
                sync_res = weather_service.update_weather_forecast(force=False)
                if sync_res.get("updated"):
                    st.toast("✅ 已自動獲取中央氣象署最新氣象資料！", icon="🌤️")
                elif not sync_res.get("success"):
                    st.warning(f"⚠️ 自動同步提示：{sync_res['message']}")

    # ── 緊湊控制項列（單列緊湊排版：標題 | 臺灣時間與資料更新 | 日期選擇 | 地區選擇 | 操作群組）──
    status = weather_service.get_sync_status()
    now_taipei = datetime.now(TAIPEI_TZ).strftime("%Y-%m-%d %H:%M")

    col_title, col_status, col_date, col_region, col_actions = st.columns(
        [2.3, 2.5, 1.8, 1.7, 1.7],
        gap="small",
        vertical_alignment="bottom",
    )
    with col_title:
        title_color = "#f8fafc" if is_dark else "#1a252f"
        sub_color = "#94a3b8" if is_dark else "#6c757d"
        st.markdown(
            f"""
            <div style="line-height: 1.2; padding-bottom: 5px;">
                <span style="font-size: 1.25rem; font-weight: 700; color: {title_color};">⛅ 臺灣天氣預報</span>
                <span style="font-size: 0.78rem; color: {sub_color}; margin-left: 4px;">CWA 中央氣象署</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_status:
        clock_color = "#38bdf8" if is_dark else "#1e293b"
        update_color = "#60a5fa" if is_dark else "#0d6efd"
        note_color = "#94a3b8" if is_dark else "#64748b"
        st.markdown(
            f"""
            <div style="font-size: 11.5px; line-height: 1.35; padding-bottom: 4px;">
                <div>⏱️ <b>現在時間：</b><span style="color: {clock_color}; font-weight: 600;">{now_taipei}</span> <span style="font-size: 10px; color: {note_color};">(臺北)</span></div>
                <div>📡 <b>氣象更新：</b><span style="color: {update_color}; font-weight: 600;">{status['last_fetch_display']}</span> <span style="font-size: 10px; color: {note_color};">(每{status['interval_hours']:.0f}h)</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    _date_placeholder = col_date.empty()
    _region_placeholder = col_region.empty()

    with col_actions:
        c_refresh, c_info, c_theme = st.columns([1.1, 0.9, 0.9], gap="small", vertical_alignment="bottom")
        with c_refresh:
            if st.button("🔄 更新", use_container_width=True, help="手動連線中央氣象署取得最新預報"):
                with st.spinner("正在請求中央氣象署 API 並安全更新資料庫..."):
                    sync_res = weather_service.update_weather_forecast(force=True)
                    if sync_res["success"] and sync_res["updated"]:
                        st.success(sync_res["message"])
                        st.rerun()
                    elif sync_res["success"] and not sync_res["updated"]:
                        st.info(sync_res["message"])
                    else:
                        st.warning(f"⚠️ {sync_res['message']}")

        with c_info:
            with st.popover("ℹ️ 說明", help="檢視資料來源、分區原則與聚合說明"):
                st.markdown("### ℹ️ 氣象資料來源與聚合說明")
                st.markdown(
                    """
                    ##### 1. 資料來源與性質
                    - **資料集**：交通部中央氣象署 (CWA) `F-D0047-091`「臺灣各縣市未來 1 週逐 12 小時天氣預報」。
                    - **預報性質**：本系統呈現為**「未來一週天氣預報」**（由數值模型預測產製），非測站之即時觀測數據。

                    ##### 2. 六大氣象分區劃分
                    - **北部地區 (6)**：臺北市、新北市、基隆市、桃園市、新竹市、新竹縣
                    - **中部地區 (5)**：臺中市、苗栗縣、彰化縣、南投縣、雲林縣
                    - **南部地區 (6)**：臺南市、高雄市、嘉義市、嘉義縣、屏東縣、澎湖縣
                    - **東北部地區 (1)**：宜蘭縣
                    - **東部地區 (1)**：花蓮縣
                    - **東南部地區 (1)**：臺東縣

                    ##### 3. 六大分區聚合原則 (Aggregation Rules)
                    - **最高溫 (MaxT)**：各縣市每日取白日時段 (06:00 起) 之最高值；同分區內各縣市取平均值，保留一位小數。
                    - **最低溫 (MinT)**：各縣市每日取各時段之最低值；同分區內各縣市取平均值，保留一位小數。
                    - **天氣現象 (Weather)**：類別文字不可直接平均，以該分區所屬各縣市白日時段出現頻率最高者（眾數 Mode）作為代表。
                    - **降雨機率 (PoP)**：計算該分區所有縣市當日有效 12 小時降雨機率之平均值（四捨五入至整數百分比）；無資料（「-」）排除不計。

                    ##### 4. 六小時自動新鮮度檢查
                    - 系統啟動時自動比對最後擷取時間，若距離前次同步已超過 6 小時，將主動背景獲取中央氣象署最新預報資料；亦可隨時點擊「🔄 更新」手動安全更新。
                    """
                )

        with c_theme:
            def toggle_theme():
                st.session_state["theme"] = "dark" if st.session_state.get("theme") == "light" else "light"

            theme_label = "🌙 深色" if not is_dark else "☀️ 淺色"
            st.button(
                theme_label,
                key="theme_toggle_btn",
                on_click=toggle_theme,
                use_container_width=True,
                help="切換淺色 / 深色主題",
            )

    # ── 資料庫連線檢查 ────────────────────────────────────────────────
    if not os.path.exists(DB_PATH):
        st.error(
            f"❌ 找不到資料庫檔案 `{DB_PATH}`！\n\n"
            "請先點擊上方「🔄 更新天氣資料」按鈕，或在終端機執行 `python database.py`。"
        )
        st.stop()

    conn = get_connection(DB_PATH)
    try:
        regions = get_available_regions(conn)
        if not regions:
            st.warning("⚠️ 資料庫中尚無任何預報資料，請點擊上方更新按鈕。")
            st.stop()

        # =====================================================
        # 【主視覺】台灣天氣互動地圖（最大化視窗呈現）
        # =====================================================

        # 取得控制項資料並渲染到標題列的佔位符
        available_dates = get_available_dates(conn)
        if not available_dates:
            st.warning("⚠️ 查無預報日期資料。")
            st.stop()

        selected_date = _date_placeholder.selectbox(
            "📅 預報日期",
            options=available_dates,
            index=0,
            help="選擇欲觀察全台氣溫分佈的預報日期",
            key="date_selector",
        )

        # ── 地區選取狀態管理 ──────────────────────────────────────────
        if "selected_region" not in st.session_state:
            st.session_state["selected_region"] = "中部地區"
        if "panel_open" not in st.session_state:
            st.session_state["panel_open"] = False
        if "last_handled_click" not in st.session_state:
            st.session_state["last_handled_click"] = None
        if "sel_version" not in st.session_state:
            st.session_state["sel_version"] = 0

        dropdown_options = ["(點選地圖分區)"] + regions
        current_idx = (
            (regions.index(st.session_state["selected_region"]) + 1)
            if (st.session_state["panel_open"] and st.session_state["selected_region"] in regions)
            else 0
        )

        sel_key = f"region_sel_{st.session_state['sel_version']}"
        selected_from_dropdown = _region_placeholder.selectbox(
            "📍 地區",
            options=dropdown_options,
            index=current_idx,
            help="選擇欲查詢之台灣分區，或直接點選地圖上的分區區塊",
            key=sel_key,
        )

        if selected_from_dropdown != "(點選地圖分區)":
            if not st.session_state["panel_open"] or st.session_state["selected_region"] != selected_from_dropdown:
                st.session_state["selected_region"] = selected_from_dropdown
                st.session_state["panel_open"] = True
                st.rerun()
        elif st.session_state["panel_open"] and current_idx != 0:
            st.session_state["panel_open"] = False
            st.rerun()

        # 查詢該日期的地圖資料
        date_df = get_forecast_by_date(conn, selected_date)
        region_data = {}
        for _, row in date_df.iterrows():
            region_data[row["regionName"]] = {
                "mint": float(row["mint"]),
                "maxt": float(row["maxt"]),
                "weather": row["weather"],
                "pop": row["pop"],
            }

        # 建立 Folium 地圖（深淺色主題自適配，限制於台灣範圍）
        if is_dark:
            # Esri World_Dark_Gray_Base – no API key required for public tile access.
            tiles_param = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
            attr_param = "Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ"
        else:
            tiles_param = "OpenStreetMap"
            attr_param = ""  # Folium handles OSM attribution automatically

        m = folium.Map(
            location=[23.65, 120.95],
            zoom_start=8,
            min_zoom=7,
            max_zoom=11,
            max_bounds=True,
            min_lat=21.0,
            max_lat=26.5,
            min_lon=118.0,
            max_lon=123.5,
            tiles=tiles_param,
            attr=attr_param,
            control_scale=True,
        )

        # 繪製六大氣象分區 GeoJSON 多邊形圖層（清晰邊界、淡雅填色、Hover 醒目提示與 Tooltip）
        region_boundaries = load_region_boundaries()
        is_panel_active = st.session_state["panel_open"]
        active_region = st.session_state["selected_region"]
        for region_name, features in region_boundaries.items():
            if not features:
                continue
            border_color = REGION_BOUNDARY_COLORS.get(region_name, "#2563EB")
            fc = {"type": "FeatureCollection", "features": features}
            is_active = (is_panel_active and region_name == active_region)
            fill_op = 0.32 if is_active else 0.15
            weight_val = 3.5 if is_active else 2.2

            folium.GeoJson(
                fc,
                name=region_name,
                style_function=lambda x, c=border_color, f_op=fill_op, w=weight_val: {
                    "fillColor": c,
                    "color": c,
                    "weight": w,
                    "fillOpacity": f_op,
                },
                highlight_function=lambda x: {
                    "weight": 3.8,
                    "fillOpacity": 0.45,
                },
                tooltip=folium.GeoJsonTooltip(
                    fields=["region", "county"],
                    aliases=["氣象分區：", "縣市："],
                    localize=True,
                    sticky=True,
                ),
            ).add_to(m)

        map_summary_records = []
        for region_name, coords in REGION_COORDINATES.items():
            if region_name not in region_data:
                continue
            r_info = region_data[region_name]
            mint = r_info["mint"]
            maxt = r_info["maxt"]
            wx_val = r_info["weather"] or "--"
            pop_val = f"{int(r_info['pop'])}%" if pd.notnull(r_info["pop"]) else "--"
            avg_temp = (mint + maxt) / 2.0
            color_name, color_hex, color_desc = get_temperature_color(avg_temp)
            short_name = REGION_SHORT_NAMES.get(region_name, region_name)

            map_summary_records.append({
                "分區名稱": region_name,
                "MinT": f"{mint:.1f}°C",
                "MaxT": f"{maxt:.1f}°C",
                "平均溫度": f"{avg_temp:.1f}°C",
                "天氣現象": wx_val,
                "降雨機率": pop_val,
                "hex": color_hex,
            })

            popup_html = f"""
            <div style="font-family: Arial, sans-serif; font-size: 13px; line-height: 1.6; min-width: 150px; padding: 4px;">
                <h4 style="margin: 0 0 6px 0; color: #2c3e50; border-bottom: 2px solid {color_hex}; padding-bottom: 3px;">
                    {region_name}
                </h4>
                <b>預報日期：</b>{selected_date}<br>
                <b>最低氣溫：</b>{mint:.1f}°C<br>
                <b>最高氣溫：</b>{maxt:.1f}°C<br>
                <b>平均溫度：</b><span style="font-weight: bold; color: {color_hex};">{avg_temp:.1f}°C</span><br>
                <b>天氣現象：</b>{wx_val}<br>
                <b>降雨機率：</b>{pop_val}
            </div>
            """
            folium.CircleMarker(
                location=coords,
                radius=14,
                color="white",
                weight=2.5,
                fill=True,
                fill_color=color_hex,
                fill_opacity=0.9,
                popup=folium.Popup(popup_html, max_width=250),
                tooltip=f"<b>{region_name}</b>: {avg_temp:.1f}°C ｜ {wx_val}",
            ).add_to(m)

            label_color = "#f8fafc" if is_dark else "#1a252f"
            shadow_color = "1px 1px 3px black, -1px -1px 3px black, 1px -1px 3px black, -1px 1px 3px black" if is_dark else "1px 1px 2px white, -1px -1px 2px white, 1px -1px 2px white, -1px 1px 2px white"
            folium.map.Marker(
                location=[coords[0] - 0.03, coords[1] + 0.15],
                icon=DivIcon(
                    html=f"""
                    <div style="
                        font-size: 12px;
                        font-weight: bold;
                        color: {label_color};
                        text-shadow: {shadow_color};
                        white-space: nowrap;
                    ">
                        {short_name}
                    </div>
                    """
                ),
            ).add_to(m)

        def close_panel():
            st.session_state["panel_open"] = False
            st.session_state["last_handled_click"] = st.session_state.get("_current_map_click")
            st.session_state["sel_version"] = st.session_state.get("sel_version", 0) + 1

        # ── 視圖呈現：已選取分區時呈現側邊詳細資訊面板，未選取時全寬地圖 ──
        if st.session_state["panel_open"] and active_region in regions:
            col_map, col_panel = st.columns([6, 4], gap="medium")
            with col_map:
                st_data = st_folium(
                    m,
                    width=None,
                    height=780,
                    use_container_width=True,
                    key="taiwan_weather_map",
                    returned_objects=["last_active_drawing", "last_object_clicked_tooltip", "last_clicked"],
                )
                st.caption(
                    "🎨 氣溫圖例："
                    "🔵 &lt;20°C 偏涼　"
                    "🟢 20–25°C 舒適　"
                    "🟡 25–30°C 偏熱　"
                    "🔴 ≥30°C 炎熱"
                )

            with col_panel:
                # 側邊面板標頭與關閉按鈕
                c_title, c_close = st.columns([3, 1], vertical_alignment="center")
                with c_title:
                    st.markdown(f"### 📍 {active_region}")
                with c_close:
                    st.button(
                        "✕ 關閉",
                        key="btn_close_side_panel",
                        use_container_width=True,
                        on_click=close_panel,
                        help="關閉資訊面板並返回全螢幕地圖",
                    )

                # 當日氣候數據卡
                if active_region in region_data:
                    curr = region_data[active_region]
                    c_mint = curr["mint"]
                    c_maxt = curr["maxt"]
                    c_avg = (c_mint + c_maxt) / 2.0
                    c_wx = curr["weather"] or "--"
                    c_pop = f"{int(curr['pop'])}%" if pd.notnull(curr["pop"]) else "--"
                    _, c_color_hex, _ = get_temperature_color(c_avg)

                    card_bg = "#1e293b" if is_dark else "#f8fafc"
                    card_border = "#334155" if is_dark else "#e2e8f0"
                    card_text = "#f1f5f9" if is_dark else "#1e293b"
                    card_sub = "#94a3b8" if is_dark else "#64748b"

                    st.markdown(
                        f"""
                        <div style="background: {card_bg}; border: 1px solid {card_border}; border-left: 4px solid {c_color_hex};
                                    border-radius: 8px; padding: 10px 14px; margin-bottom: 12px;">
                            <div style="display: flex; justify-content: space-between; align-items: baseline;">
                                <span style="font-size: 13px; color: {card_sub};">預報日期：<b>{selected_date}</b></span>
                                <span style="background-color: {c_color_hex}; color: white; padding: 2px 8px; border-radius: 10px; font-size: 12px; font-weight: bold;">
                                    平均 {c_avg:.1f}°C
                                </span>
                            </div>
                            <div style="margin-top: 6px; font-size: 13.5px; color: {card_text}; line-height: 1.6;">
                                🌡️ 氣溫：<b>{c_mint:.1f}°C ~ {c_maxt:.1f}°C</b><br>
                                🌤️ 天氣：<b>{c_wx}</b> ｜ 💧 降雨機率：<b>{c_pop}</b>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                # 七日氣溫折線圖
                st.markdown("##### 📈 一週氣溫折線圖")
                df = get_region_forecast(conn, active_region)
                if not df.empty:
                    df["MinT"] = df["MinT"].astype(float)
                    df["MaxT"] = df["MaxT"].astype(float)
                    fig, ax = plt.subplots(figsize=(6.0, 3.5), dpi=100)

                    if is_dark:
                        fig.patch.set_facecolor("#1e293b")
                        ax.set_facecolor("#0f172a")
                        ax.tick_params(colors="#cbd5e1", labelsize=8.5)
                        ax.yaxis.label.set_color("#f8fafc")
                        ax.xaxis.label.set_color("#f8fafc")
                        ax.grid(True, linestyle="--", alpha=0.25, color="#475569")
                        legend_bg = "#1e293b"
                        legend_edge = "#475569"
                        legend_text = "#f8fafc"
                        max_label_color = "#f87171"
                        min_label_color = "#38bdf8"
                        line_max = "#f87171"
                        line_min = "#38bdf8"
                        spine_c = "#334155"
                    else:
                        ax.tick_params(labelsize=8.5)
                        ax.grid(True, linestyle="--", alpha=0.35)
                        legend_bg = "white"
                        legend_edge = "#cccccc"
                        legend_text = "#1a252f"
                        max_label_color = "#C0392B"
                        min_label_color = "#2980B9"
                        line_max = "#E74C3C"
                        line_min = "#3498DB"
                        spine_c = "#cccccc"

                    short_dates = [
                        d[5:].replace("-", "/") if len(d) >= 10 else d
                        for d in df["Date"]
                    ]
                    ax.plot(short_dates, df["MaxT"], color=line_max, marker="o",
                            markersize=5, linewidth=2.0, label="MaxT")
                    ax.plot(short_dates, df["MinT"], color=line_min, marker="o",
                            markersize=5, linewidth=2.0, label="MinT")
                    for i, val in enumerate(df["MaxT"]):
                        ax.annotate(f"{val:.1f}°", (short_dates[i], val),
                                    textcoords="offset points", xytext=(0, 5),
                                    ha="center", fontsize=8, fontweight="bold", color=max_label_color)
                    for i, val in enumerate(df["MinT"]):
                        ax.annotate(f"{val:.1f}°", (short_dates[i], val),
                                    textcoords="offset points", xytext=(0, -12),
                                    ha="center", fontsize=8, fontweight="bold", color=min_label_color)
                    ax.set_ylabel("Temperature (°C)", fontsize=9.5, fontweight="bold")
                    ax.set_xlabel("Date", fontsize=9.5, fontweight="bold")
                    y_min = max(0, int(df["MinT"].min()) - 3)
                    y_max = int(df["MaxT"].max()) + 3
                    ax.set_ylim(y_min, y_max)
                    ax.legend(loc="upper right", frameon=True, fontsize=8, facecolor=legend_bg, edgecolor=legend_edge, labelcolor=legend_text)
                    for spine in ax.spines.values():
                        spine.set_color(spine_c)
                    plt.tight_layout()
                    st.pyplot(fig)
                    plt.close(fig)

                    # 七日數據表
                    st.markdown("##### 📋 一週詳細預報數據")
                    display_df = df.copy()
                    display_df["降雨機率"] = display_df["pop"].apply(
                        lambda p: f"{int(p)}%" if pd.notnull(p) else "--"
                    )
                    display_df["天氣現象"] = display_df["weather"].fillna("--")
                    table_view = display_df[
                        ["Date", "MinT", "MaxT", "天氣現象", "降雨機率"]
                    ].rename(columns={"Date": "預報日期"})
                    st.dataframe(table_view, use_container_width=True, hide_index=True)
        else:
            # 未選定地區時，地圖全螢幕呈現（無下方多餘展開區）
            st_data = st_folium(
                m,
                width=None,
                height=780,
                use_container_width=True,
                key="taiwan_weather_map",
                returned_objects=["last_active_drawing", "last_object_clicked_tooltip", "last_clicked"],
            )
            st.caption(
                "🎨 氣溫圖例："
                "🔵 &lt;20°C 偏涼　"
                "🟢 20–25°C 舒適　"
                "🟡 25–30°C 偏熱　"
                "🔴 ≥30°C 炎熱　"
                "💡 提示：點擊地圖上的任一天氣分區區塊，即可展開該分區氣象資訊與一週氣溫趨勢折線圖。"
            )

        # ── 處理地圖點擊互動 ──────────────────────────────────────────
        raw_click = st_data.get("last_clicked") if st_data else None
        current_click_id = (
            round(raw_click["lat"], 6),
            round(raw_click["lng"], 6),
        ) if (raw_click and "lat" in raw_click and "lng" in raw_click) else None

        st.session_state["_current_map_click"] = current_click_id

        if current_click_id and current_click_id != st.session_state.get("last_handled_click"):
            st.session_state["last_handled_click"] = current_click_id
            clicked_region = None
            drawing = st_data.get("last_active_drawing")
            if drawing and isinstance(drawing, dict) and "properties" in drawing:
                clicked_region = drawing["properties"].get("region")

            if not clicked_region and st_data.get("last_object_clicked_tooltip"):
                tooltip_str = str(st_data["last_object_clicked_tooltip"])
                for r in regions:
                    if r in tooltip_str:
                        clicked_region = r
                        break

            if clicked_region and clicked_region in regions:
                st.session_state["selected_region"] = clicked_region
                st.session_state["panel_open"] = True
                st.session_state["sel_version"] = st.session_state.get("sel_version", 0) + 1
                st.rerun()

    finally:
        conn.close()

    st.markdown("---")
    st.caption(
        "資料來源：中央氣象署 (CWA) 臺灣一週天氣預報 ｜ 儲存於 SQLite 資料庫 (`data.db`) ｜ HW10 Stage 3-B-1"
    )


if __name__ == "__main__":
    main()
