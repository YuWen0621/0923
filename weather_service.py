# -*- coding: utf-8 -*-
"""
weather_service.py
==================
[Stage 1 & Stage 2] Centralized weather update workflow & normalized data service.

Responsibilities:
1. Coordinate data fetching (fetch_weather), parsing (parse_weather), and storage (database).
2. Manage data freshness checks with configurable refresh interval (default: 6 hours).
3. Ensure atomic and safe updates (never wipe valid existing data if fetch or parse fails).
4. Provide normalized, JSON-serializable forecast structures for future Vercel / API compatibility.
"""

import os
import sys
import json
import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

import database
import parse_weather
import fetch_weather

# 確保 Windows 主控台正確顯示 UTF-8 中文字元
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

TAIPEI_TZ = ZoneInfo("Asia/Taipei")
DEFAULT_REFRESH_INTERVAL_HOURS = 6


def get_refresh_interval_hours():
    """取得資料新鮮度檢查間隔小時數（預設 6 小時，可於 .env 自訂）。"""
    raw_val = os.getenv("CWA_REFRESH_INTERVAL_HOURS")
    if raw_val:
        try:
            return float(raw_val)
        except ValueError:
            pass
    return float(DEFAULT_REFRESH_INTERVAL_HOURS)


def parse_timestamp_to_taipei(iso_str):
    """將 ISO 時間字串轉換為 Asia/Taipei 時區之 datetime 物件。"""
    if not iso_str:
        return None
    try:
        # 處理標準 ISO 格式
        dt = datetime.datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TAIPEI_TZ)
        else:
            dt = dt.astimezone(TAIPEI_TZ)
        return dt
    except Exception:
        return None


def get_sync_status(conn=None):
    """
    查詢目前資料庫的更新狀態與新鮮度。
    
    回傳：
        dict: {
            "last_fetch_iso": str or None,
            "last_fetch_dt": datetime or None,
            "last_fetch_display": str,
            "age_hours": float or None,
            "is_stale": bool,
            "interval_hours": float,
        }
    """
    should_close = False
    if conn is None:
        conn = database.get_connection()
        should_close = True

    try:
        database.init_db(conn)
        last_iso = database.get_last_fetch_time(conn)
        last_dt = parse_timestamp_to_taipei(last_iso)
        interval = get_refresh_interval_hours()

        if last_dt:
            now = datetime.datetime.now(TAIPEI_TZ)
            age_hours = (now - last_dt).total_seconds() / 3600.0
            is_stale = age_hours >= interval
            display_str = last_dt.strftime("%Y-%m-%d %H:%M:%S (Asia/Taipei)")
        else:
            age_hours = None
            is_stale = True
            display_str = "尚未記錄擷取時間"

        return {
            "last_fetch_iso": last_iso,
            "last_fetch_dt": last_dt,
            "last_fetch_display": display_str,
            "age_hours": age_hours,
            "is_stale": is_stale,
            "interval_hours": interval,
        }
    finally:
        if should_close and conn:
            conn.close()


def update_weather_forecast(force=False, timeout=30):
    """
    集中式天氣預報更新工作流程。
    
    流程與防護：
    1. 檢查資料庫最新狀態；若非強制且仍在有效區間內，直接返回不發起 API 呼叫。
    2. 呼叫 CWA API 取得最新 JSON 資料。
    3. 若 API 失敗（斷網、404、500 等），絕不刪除資料庫既有資料，並回傳明確錯誤原因。
    4. 驗證並解析資料。若解析異常，保留舊資料並返回失敗。
    5. 將原始 JSON 備份寫入 weather_raw.json。
    6. 使用資料庫事務安全寫入 data.db，並更新時間戳。
    """
    status = get_sync_status()
    if not force and not status["is_stale"]:
        return {
            "success": True,
            "updated": False,
            "message": f"目前資料仍在 {status['interval_hours']} 小時時效內，未重複請求 API。",
            "timestamp": status["last_fetch_display"],
        }

    # 1. 向 CWA 請求資料
    print("📡 正在向中央氣象署請求最新一週天氣預報...")
    raw_json = fetch_weather.fetch_cwa_forecast(timeout=timeout)

    if not raw_json:
        return {
            "success": False,
            "updated": False,
            "message": "中央氣象署 API 連線異常或未回傳有效預報，系統已自動維持既有已儲存資料。",
            "timestamp": status["last_fetch_display"],
        }

    # 2. 解析資料
    try:
        records = parse_weather.parse_cwa_json(raw_json)
        if not records or len(records) < 42:
            return {
                "success": False,
                "updated": False,
                "message": f"API 回傳資料不完整（取得 {len(records)} 筆，少於預期 42 筆），已取消更新以保護既有資料。",
                "timestamp": status["last_fetch_display"],
            }
    except Exception as e:
        return {
            "success": False,
            "updated": False,
            "message": f"資料解析過程發生異常：{e}，維持原資料庫內容。",
            "timestamp": status["last_fetch_display"],
        }

    # 3. 備份原始 JSON 檔案至 weather_raw.json
    try:
        with open(database.RAW_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(raw_json, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ 備份原始 JSON 發生錯誤（不影響資料庫寫入）：{e}")

    # 4. 事務性寫入資料庫
    fetch_time_dt = datetime.datetime.now(TAIPEI_TZ)
    fetch_time_iso = fetch_time_dt.isoformat()
    fetch_time_display = fetch_time_dt.strftime("%Y-%m-%d %H:%M:%S (Asia/Taipei)")

    conn = database.get_connection()
    try:
        database.init_db(conn)
        saved_count = database.save_forecasts(conn, records, fetch_time_iso=fetch_time_iso)
        return {
            "success": True,
            "updated": True,
            "message": f"成功更新 CWA 最新天氣資料！共寫入 {saved_count} 筆分區預報紀錄。",
            "timestamp": fetch_time_display,
            "count": saved_count,
        }
    except Exception as e:
        return {
            "success": False,
            "updated": False,
            "message": f"資料庫寫入失敗：{e}，交易已自動復原 (Rollback)。",
            "timestamp": status["last_fetch_display"],
        }
    finally:
        conn.close()


def get_normalized_forecast(conn=None):
    """
    提供標準化、JSON 可序列化之全台氣象結構，供未來 Vercel / Next.js / REST API 重用。
    """
    should_close = False
    if conn is None:
        conn = database.get_connection()
        should_close = True

    try:
        status = get_sync_status(conn)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT regionName, dataDate, mint, maxt, weather, pop
            FROM TemperatureForecasts
            ORDER BY dataDate ASC, id ASC;
        """)
        rows = cursor.fetchall()

        regions_dict = {}
        for r_name, d_date, mint, maxt, wx, pop in rows:
            if r_name not in regions_dict:
                regions_dict[r_name] = []
            regions_dict[r_name].append({
                "date": d_date,
                "min_temp": float(mint),
                "max_temp": float(maxt),
                "avg_temp": round((float(mint) + float(maxt)) / 2.0, 1),
                "weather": wx,
                "pop": pop,
            })

        return {
            "meta": {
                "fetched_at": status["last_fetch_iso"],
                "fetched_at_display": status["last_fetch_display"],
                "timezone": "Asia/Taipei",
                "dataset": os.getenv("CWA_DATASET_ID", "F-D0047-091"),
                "total_records": len(rows),
                "region_count": len(regions_dict),
            },
            "regions": regions_dict,
        }
    finally:
        if should_close and conn:
            conn.close()


if __name__ == "__main__":
    print("=" * 60)
    print("【天氣服務同步狀態測試】")
    print("=" * 60)
    st_info = get_sync_status()
    print("最後擷取時間:", st_info["last_fetch_display"])
    print(f"資料距今: {st_info['age_hours']:.2f} 小時" if st_info["age_hours"] is not None else "資料距今: 無紀錄")
    print("是否已逾期需更新:", st_info["is_stale"])
    print(f"配置檢查間隔: {st_info['interval_hours']} 小時")
    print("=" * 60)
