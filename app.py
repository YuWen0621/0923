# -*- coding: utf-8 -*-
"""
app.py
======
[HW10 Task 4 & Task 5] Taiwan Weather Forecast Web Application (Streamlit + Folium)

Features:
- Pure SQLite data connection: connects to data.db and queries TemperatureForecasts.
- No direct CWA API calls, no requests.get().
- Task 4:
    * Region dropdown menu using st.selectbox() populated dynamically from SQLite.
    * Interactive line chart of 7-day MinT and MaxT (X-axis: date, Y-axis: °C).
    * Structured data table with Date, MinT, MaxT.
    * Automatic updates upon changing region selection.
- Task 5 (Advanced Optional):
    * Interactive Taiwan map powered by Folium & streamlit-folium.
    * Date selector for available forecast dates from SQLite.
    * 6 region markers placed at representative coordinates.
    * Average temperature calculation: (MinT + MaxT) / 2 with 1 decimal place.
    * Dynamic marker colors: <20°C (blue), 20-25°C (green), 25-30°C (orange), >=30°C (red).
    * Interactive popup with Region name, Date, MinT, MaxT, and Avg Temp.
    * Clear color legend and graceful handling of missing data.
"""

import os
import sqlite3
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import folium
from folium import DivIcon
from streamlit_folium import st_folium

# =============================================================
# 專案路徑設定
# =============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data.db")

# =============================================================
# 六大分區代表性經緯度座標 (供地圖標記定位使用，氣溫皆來自 SQLite)
# =============================================================
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


# =============================================================
# 資料庫查詢函數 (純 SQLite，絕不呼叫 CWA API)
# =============================================================
def get_connection(db_path=DB_PATH):
    """建立 SQLite 資料庫連線。"""
    if not os.path.exists(db_path):
        return None
    return sqlite3.connect(db_path)


def get_available_regions(conn):
    """
    從 SQLite 資料庫查詢所有不重複的地區名稱。
    對應 SQL: SELECT DISTINCT regionName FROM TemperatureForecasts ORDER BY id;
    """
    query = "SELECT DISTINCT regionName FROM TemperatureForecasts ORDER BY id;"
    df = pd.read_sql_query(query, conn)
    return df["regionName"].tolist()


def get_region_forecast(conn, region_name):
    """
    依選定地區從 SQLite 查詢 7 天氣溫預報資料。
    對應 SQL: SELECT dataDate AS Date, mint AS MinT, maxt AS MaxT FROM TemperatureForecasts WHERE regionName = ?;
    """
    query = """
    SELECT dataDate AS Date, mint AS MinT, maxt AS MaxT
    FROM TemperatureForecasts
    WHERE regionName = ?
    ORDER BY dataDate ASC;
    """
    df = pd.read_sql_query(query, conn, params=(region_name,))
    return df


def get_available_dates(conn):
    """
    從 SQLite 資料庫查詢所有可供選擇的預報日期。
    對應 SQL: SELECT DISTINCT dataDate FROM TemperatureForecasts ORDER BY dataDate ASC;
    """
    query = "SELECT DISTINCT dataDate FROM TemperatureForecasts ORDER BY dataDate ASC;"
    df = pd.read_sql_query(query, conn)
    return df["dataDate"].tolist()


def get_forecast_by_date(conn, selected_date):
    """
    依選定日期從 SQLite 查詢六大區域的天氣預報資料。
    對應 SQL: SELECT regionName, mint, maxt FROM TemperatureForecasts WHERE dataDate = ?;
    """
    query = """
    SELECT regionName, mint, maxt
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
    # 頁面配置
    st.set_page_config(
        page_title="Taiwan Weather Forecast Dashboard",
        page_icon="⛅",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # 標題與簡介
    st.title("⛅ Taiwan Weather Forecast Dashboard")
    st.caption("從氣象資料到互動式天氣預報應用程式 ｜ HW10 (Task 4 & Task 5)")
    st.markdown("---")

    # 檢查 data.db 是否存在
    if not os.path.exists(DB_PATH):
        st.error(
            f"❌ 找不到資料庫檔案 `{DB_PATH}`！\n\n"
            "請先在終端機依序執行資料處理管線：\n"
            "1. `python fetch_weather.py`\n"
            "2. `python parse_weather.py`\n"
            "3. `python database.py`"
        )
        st.stop()

    # 連線至 SQLite 資料庫
    conn = get_connection(DB_PATH)
    try:
        # =====================================================
        # 【Task 4】區域氣溫預報 (下拉選單 + 折線圖 + 數據表)
        # =====================================================
        st.header("📊 區域氣溫預報 (一週折線圖與數據表)")
        
        # 1. 取得所有可選地區清單
        regions = get_available_regions(conn)

        if not regions:
            st.warning("⚠️ 資料庫中尚無任何預報資料，請先執行 `database.py`。")
            st.stop()

        # 下拉選單選擇地區，預設選中「中部地區」（符合作業範例說明）
        default_region_idx = regions.index("中部地區") if "中部地區" in regions else 0
        selected_region = st.selectbox(
            "Select Region",
            options=regions,
            index=default_region_idx,
            help="請選擇欲查詢之台灣分區",
            key="region_selector",
        )

        # 2. 查詢該地區的一週氣溫預報資料
        df = get_region_forecast(conn, selected_region)

        if df.empty:
            st.info(f"查無【{selected_region}】之天氣預報資料。")
        else:
            df["MinT"] = df["MinT"].astype(float)
            df["MaxT"] = df["MaxT"].astype(float)

            st.subheader(f"Temperature Forecast - {selected_region}")

            # 雙欄排版：左欄繪製高低溫折線圖，右欄顯示資料表格
            col_chart, col_table = st.columns([3, 2], gap="large")

            with col_chart:
                st.markdown("##### 📈 一週氣溫折線圖")

                # 建立 Matplotlib 專業折線圖
                fig, ax = plt.subplots(figsize=(7.5, 4.8), dpi=100)

                # X 軸標籤格式化為 MM/DD (例: 09/23)
                short_dates = [
                    d[5:].replace("-", "/") if len(d) >= 10 else d
                    for d in df["Date"]
                ]

                # 繪製 MaxT (紅色線條與圓點) 與 MinT (藍色線條與圓點)
                ax.plot(
                    short_dates,
                    df["MaxT"],
                    color="#E74C3C",
                    marker="o",
                    markersize=6,
                    linewidth=2.2,
                    label="MaxT",
                )
                ax.plot(
                    short_dates,
                    df["MinT"],
                    color="#3498DB",
                    marker="o",
                    markersize=6,
                    linewidth=2.2,
                    label="MinT",
                )

                # 標註具體度數數值（保留一位小數）
                for i, val in enumerate(df["MaxT"]):
                    ax.annotate(
                        f"{val:.1f}°",
                        (short_dates[i], val),
                        textcoords="offset points",
                        xytext=(0, 7),
                        ha="center",
                        fontsize=9,
                        fontweight="bold",
                        color="#C0392B",
                    )
                for i, val in enumerate(df["MinT"]):
                    ax.annotate(
                        f"{val:.1f}°",
                        (short_dates[i], val),
                        textcoords="offset points",
                        xytext=(0, -14),
                        ha="center",
                        fontsize=9,
                        fontweight="bold",
                        color="#2980B9",
                    )

                # 設定圖表樣式與座標軸標籤
                ax.set_ylabel("Temperature (°C)", fontsize=11, fontweight="bold")
                ax.set_xlabel("Date", fontsize=11, fontweight="bold")

                y_min = max(0, int(df["MinT"].min()) - 4)
                y_max = int(df["MaxT"].max()) + 4
                ax.set_ylim(y_min, y_max)

                ax.grid(True, linestyle="--", alpha=0.4)
                ax.legend(loc="upper right", frameon=True, facecolor="white", edgecolor="#cccccc")

                for spine in ax.spines.values():
                    spine.set_color("#cccccc")

                plt.tight_layout()
                st.pyplot(fig)
                plt.close(fig)

            with col_table:
                st.markdown("##### 📋 一週預報數據表")
                display_df = df[["Date", "MinT", "MaxT"]].copy()
                st.dataframe(
                    display_df,
                    use_container_width=True,
                    hide_index=True,
                )

                avg_min = df["MinT"].mean()
                avg_max = df["MaxT"].mean()
                st.markdown(
                    f"""
                    <div style="background-color: #f8f9fa; border: 1px solid #e9ecef; border-radius: 8px; padding: 12px; margin-top: 10px;">
                        <div style="font-size: 13px; color: #6c757d;">區域週平均概況</div>
                        <div style="font-size: 15px; font-weight: bold; margin-top: 4px;">
                            平均最低溫：<span style="color: #3498DB;">{avg_min:.1f} °C</span> ｜ 
                            平均最高溫：<span style="color: #E74C3C;">{avg_max:.1f} °C</span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        # =====================================================
        # 【Task 5】台灣地圖視覺化 (Folium 空間視覺化)
        # =====================================================
        st.markdown("---")
        st.header("🗺️ 台灣各區氣溫地圖 (互動空間視覺化 - Task 5)")
        st.caption("依各分區當日平均氣溫 `(MinT + MaxT) / 2` 自動以代表色彩標記於地圖上")

        # 1. 取得資料庫中現有的預報日期列表
        available_dates = get_available_dates(conn)

        if not available_dates:
            st.warning("⚠️ 查無預報日期資料。")
            st.stop()

        # 日期選擇器 (st.selectbox)
        selected_date = st.selectbox(
            "Select Forecast Date",
            options=available_dates,
            index=0,
            help="選擇欲觀察全台氣溫分佈的預報日期",
            key="date_selector",
        )

        # 2. 查詢該日期所有區域的預報數據
        date_df = get_forecast_by_date(conn, selected_date)

        # 轉成字典方便快速查找 (regionName -> {mint, maxt})
        region_data = {}
        for _, row in date_df.iterrows():
            region_data[row["regionName"]] = {
                "mint": float(row["mint"]),
                "maxt": float(row["maxt"]),
            }

        # 3. 建立 Folium 地圖物件 (中心定位於台灣)
        m = folium.Map(
            location=[23.75, 120.95],
            zoom_start=7,
            tiles="OpenStreetMap",
            control_scale=True,
        )

        # 遍歷六大區域，計算均溫並繪製地圖標記
        map_summary_records = []
        for region_name, coords in REGION_COORDINATES.items():
            # 優雅處理缺少資料的情境，絕不造假數據
            if region_name not in region_data:
                continue

            mint = region_data[region_name]["mint"]
            maxt = region_data[region_name]["maxt"]
            avg_temp = (mint + maxt) / 2.0

            color_name, color_hex, color_desc = get_temperature_color(avg_temp)
            short_name = REGION_SHORT_NAMES.get(region_name, region_name)

            map_summary_records.append({
                "地區": region_name,
                "MinT": f"{mint:.1f}°C",
                "MaxT": f"{maxt:.1f}°C",
                "平均溫度": f"{avg_temp:.1f}°C",
                "色彩級別": color_desc,
                "hex": color_hex,
            })

            # Popup 內容規範 (符合 Requirement 10)
            popup_html = f"""
            <div style="font-family: Arial, sans-serif; font-size: 13px; line-height: 1.6; min-width: 140px; padding: 4px;">
                <h4 style="margin: 0 0 6px 0; color: #2c3e50; border-bottom: 2px solid {color_hex}; padding-bottom: 3px;">
                    {region_name}
                </h4>
                <b>預報日期：</b>{selected_date}<br>
                <b>最低氣溫：</b>{mint:.1f}°C<br>
                <b>最高氣溫：</b>{maxt:.1f}°C<br>
                <b>平均溫度：</b><span style="font-weight: bold; color: {color_hex};">{avg_temp:.1f}°C</span>
            </div>
            """

            # 繪製圓形溫度色彩標記
            folium.CircleMarker(
                location=coords,
                radius=14,
                color="white",
                weight=2.5,
                fill=True,
                fill_color=color_hex,
                fill_opacity=0.9,
                popup=folium.Popup(popup_html, max_width=240),
                tooltip=f"<b>{region_name}</b>: {avg_temp:.1f}°C (點擊查看詳情)",
            ).add_to(m)

            # 在標記右側顯示簡潔地區文字標籤 (例: 中部、南部)
            folium.map.Marker(
                location=[coords[0] - 0.03, coords[1] + 0.15],
                icon=DivIcon(
                    html=f"""
                    <div style="
                        font-size: 12px;
                        font-weight: bold;
                        color: #1a252f;
                        text-shadow: 1px 1px 2px white, -1px -1px 2px white, 1px -1px 2px white, -1px 1px 2px white;
                        white-space: nowrap;
                    ">
                        {short_name}
                    </div>
                    """
                ),
            ).add_to(m)

        # 4. 版面呈現：左欄互動地圖，右欄色彩圖例與當日分區概覽
        col_map, col_legend = st.columns([3, 2], gap="large")

        with col_map:
            st_folium(m, width=None, height=520, use_container_width=True)

        with col_legend:
            # 色彩圖例說明 (符合 Requirement 11)
            st.markdown("##### 🎨 依平均溫度設定顏色")
            st.markdown(
                """
                <div style="font-size: 14px; line-height: 1.9; margin-bottom: 15px;">
                    <div><span style="display:inline-block; width:15px; height:15px; background-color:#2E86AB; border-radius:50%; margin-right:8px; vertical-align:middle;"></span><b>&lt; 20°C</b>：藍色 (寒冷 / 偏涼)</div>
                    <div><span style="display:inline-block; width:15px; height:15px; background-color:#48A9A6; border-radius:50%; margin-right:8px; vertical-align:middle;"></span><b>20 - 25°C</b>：綠色 (宜人舒適)</div>
                    <div><span style="display:inline-block; width:15px; height:15px; background-color:#F4D35E; border-radius:50%; margin-right:8px; vertical-align:middle;"></span><b>25 - 30°C</b>：橘黃色 (溫暖偏熱)</div>
                    <div><span style="display:inline-block; width:15px; height:15px; background-color:#EE6055; border-radius:50%; margin-right:8px; vertical-align:middle;"></span><b>≥ 30°C</b>：紅色 (高溫炎熱)</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # 當日全台六區氣溫快速清單
            st.markdown(f"##### 📌 {selected_date} 各區氣溫快速概覽")
            if map_summary_records:
                sum_df = pd.DataFrame(map_summary_records)[["地區", "MinT", "MaxT", "平均溫度"]]
                st.dataframe(sum_df, use_container_width=True, hide_index=True)
            else:
                st.warning("⚠️ 該日期未查詢到任何區域氣溫紀錄。")

    finally:
        conn.close()

    # 頁尾說明
    st.markdown("---")
    st.caption("資料來源：SQLite 資料庫 (`data.db` - `TemperatureForecasts` 資料表) ｜ HW10 Task 4 & Task 5")


if __name__ == "__main__":
    main()
