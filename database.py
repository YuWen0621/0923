# -*- coding: utf-8 -*-
"""
database.py
===========
[HW10 Task 3 & Stage 1/2] Store weather forecast data into SQLite database (data.db).

Database: data.db
Table: TemperatureForecasts
Schema:
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    regionName TEXT NOT NULL,
    dataDate TEXT NOT NULL,
    mint REAL NOT NULL,
    maxt REAL NOT NULL,
    weather TEXT,
    pop INTEGER,
    UNIQUE(regionName, dataDate)

Metadata Table: SyncMetadata
Schema:
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
"""

import os
import sys
import sqlite3
import datetime
from zoneinfo import ZoneInfo
from collections import Counter
from parse_weather import (
    load_raw_json,
    parse_cwa_json,
    REGION_MAPPING,
)

# 確保 Windows 主控台正確顯示 UTF-8 中文字元
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data.db")
RAW_JSON_PATH = os.path.join(BASE_DIR, "weather_raw.json")
TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def get_connection(db_path=DB_PATH):
    """建立並回傳 SQLite 資料庫連線。"""
    return sqlite3.connect(db_path)


def init_db(conn):
    """
    建立 TemperatureForecasts 資料表、SyncMetadata 表與唯一索引（若不存在）。
    自動檢測並執行欄位遷移 (Migration)，擴充 weather 與 pop 欄位。
    """
    cursor = conn.cursor()

    # 1. 建立預報主表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS TemperatureForecasts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        regionName TEXT NOT NULL,
        dataDate TEXT NOT NULL,
        mint REAL NOT NULL,
        maxt REAL NOT NULL,
        weather TEXT,
        pop INTEGER,
        UNIQUE(regionName, dataDate)
    );
    """)

    # 欄位遷移檢驗
    cursor.execute("PRAGMA table_info(TemperatureForecasts);")
    existing_cols = [row[1] for row in cursor.fetchall()]
    if "weather" not in existing_cols:
        cursor.execute("ALTER TABLE TemperatureForecasts ADD COLUMN weather TEXT;")
    if "pop" not in existing_cols:
        cursor.execute("ALTER TABLE TemperatureForecasts ADD COLUMN pop INTEGER;")

    # 2. 建立同步元資料表 (儲存最後更新時間等狀態)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS SyncMetadata (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """)

    # 3. 確保唯一索引
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_region_date ON TemperatureForecasts(regionName, dataDate);"
    )
    conn.commit()


def save_forecasts(conn, records, fetch_time_iso=None):
    """
    將天氣預報資料安全、具事務性地存入 TemperatureForecasts 資料表。
    
    安全性規範：
      - 寫入前進行數據校驗（需含完整六大分區），校驗失敗則拋出異常拒絕寫入。
      - 採用資料庫事務 (with conn:)，一旦發生錯誤立即 Rollback，絕不毀損既有有效資料。
      - 使用 ON CONFLICT 更新現有記錄，防止產生重複資料列。
      - 同步更新 SyncMetadata 中的 last_successful_fetch 時間戳。
    """
    if not records or len(records) < 6:
        raise ValueError("資料驗證失敗：預報記錄筆數不足，拒絕寫入資料庫以保護既有資料。")

    # 確保六大分區皆存在於新數據中
    regions_in_data = set(r["regionName"] for r in records)
    for req_region in REGION_MAPPING:
        if req_region not in regions_in_data:
            raise ValueError(f"資料驗證失敗：缺少必要分區【{req_region}】，取消資料庫更新。")

    insert_sql = """
    INSERT INTO TemperatureForecasts (regionName, dataDate, mint, maxt, weather, pop)
    VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(regionName, dataDate) DO UPDATE SET
        mint = excluded.mint,
        maxt = excluded.maxt,
        weather = excluded.weather,
        pop = excluded.pop;
    """

    payload = [
        (
            r["regionName"],
            r["dataDate"],
            float(r["mint"]),
            float(r["maxt"]),
            r.get("weather"),
            int(r["pop"]) if r.get("pop") is not None else None,
        )
        for r in records
    ]

    with conn:  # 開啟 Transaction 事務
        cursor = conn.cursor()
        cursor.executemany(insert_sql, payload)

        if fetch_time_iso:
            cursor.execute("""
            INSERT INTO SyncMetadata (key, value)
            VALUES ('last_successful_fetch', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value;
            """, (fetch_time_iso,))

    return len(payload)


def get_last_fetch_time(conn):
    """
    從資料庫讀取最後一次成功抓取資料的 ISO 時間戳。
    若資料庫尚未記錄，退回嘗試讀取 weather_raw.json 檔案修改時間。
    """
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT value FROM SyncMetadata WHERE key = 'last_successful_fetch';")
        row = cursor.fetchone()
        if row and row[0]:
            return row[0]
    except sqlite3.OperationalError:
        pass

    # 備援：讀取 weather_raw.json 修改時間
    if os.path.exists(RAW_JSON_PATH):
        mtime = os.path.getmtime(RAW_JSON_PATH)
        dt = datetime.datetime.fromtimestamp(mtime, tz=TAIPEI_TZ)
        return dt.isoformat()

    return None


def run_verification_queries(conn):
    """
    執行作業規範要求的兩項 SQL 驗證查詢，並格式化輸出結果。
    """
    cursor = conn.cursor()

    # 驗證查詢 1: 列出所有地區名稱
    query1 = "SELECT DISTINCT regionName FROM TemperatureForecasts;"
    print("=" * 75)
    print("【SQL 驗證查詢 1】列出所有地區名稱")
    print(f"SQL: {query1}")
    print("=" * 75)
    cursor.execute(query1)
    distinct_regions = [row[0] for row in cursor.fetchall()]
    for idx, reg in enumerate(distinct_regions, 1):
        print(f"  [{idx}] {reg}")
    print(f"\n地區數量確認: {len(distinct_regions)} / 6 個地區")
    print("-" * 75)

    # 驗證查詢 2: 查詢中部地區資料
    query2 = "SELECT id, regionName, dataDate, mint, maxt, weather, pop FROM TemperatureForecasts WHERE regionName = '中部地區';"
    print("\n" + "=" * 75)
    print("【SQL 驗證查詢 2】查詢中部地區資料")
    print(f"SQL: {query2}")
    print("=" * 75)
    cursor.execute(query2)
    central_rows = cursor.fetchall()

    print(f"{'id':<5} {'regionName':<10} {'dataDate':<12} {'MinT':>6} {'MaxT':>6} {'PoP':>6}  {'天氣現象'}")
    print("-" * 65)
    for row in central_rows:
        row_id, r_name, d_date, mint, maxt, wx, pop = row
        pop_str = f"{pop}%" if pop is not None else "--"
        wx_str = wx or "--"
        print(f"{row_id:<5} {r_name:<10} {d_date:<12} {mint:>6.1f} {maxt:>6.1f} {pop_str:>6}  {wx_str}")
    print(f"\n中部地區資料筆數確認: {len(central_rows)} 筆預報")
    print("-" * 75)

    # 最後更新時間
    last_fetch = get_last_fetch_time(conn)
    if last_fetch:
        print(f"🕒 資料庫記錄之最後成功擷取時間: {last_fetch} (Asia/Taipei)")
    print("=" * 75)


def load_task2_records():
    """載入既有 weather_raw.json 資料供測試與初始化使用。"""
    data = load_raw_json(RAW_JSON_PATH)
    return parse_cwa_json(data)


def main():
    print("=" * 75)
    print("【HW10 任務 3：存入 SQLite 資料庫 (data.db)】")
    print("=" * 75)
    print(f"1. 讀取解析資料 (來源: {os.path.basename(RAW_JSON_PATH)}) ...")
    records = load_task2_records()
    print(f"   成功取得 {len(records)} 筆預報紀錄。")

    print(f"\n2. 連線並初始化資料庫: {DB_PATH} ...")
    conn = get_connection(DB_PATH)
    try:
        init_db(conn)
        print("   資料表 TemperatureForecasts、SyncMetadata 與唯一性索引就緒。")

        # 取得目前時間戳或現有檔案修改時間
        last_t = get_last_fetch_time(conn) or datetime.datetime.now(TAIPEI_TZ).isoformat()
        inserted_count = save_forecasts(conn, records, fetch_time_iso=last_t)
        print(f"   已安全寫入 / 更新 {inserted_count} 筆預報紀錄至 data.db。")

        print("\n3. 執行 SQL 驗證查詢 ...\n")
        run_verification_queries(conn)
    finally:
        conn.close()

    print(f"\nTask 3 執行完成！資料庫檔案位置: {DB_PATH}")


if __name__ == "__main__":
    main()
