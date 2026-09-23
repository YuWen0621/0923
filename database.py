# -*- coding: utf-8 -*-
"""
database.py
===========
[HW10 Task 3] Store extracted weather forecast data into SQLite database (data.db).

Database: data.db
Table: TemperatureForecasts
Schema:
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    regionName TEXT NOT NULL,
    dataDate TEXT NOT NULL,
    mint REAL NOT NULL,
    maxt REAL NOT NULL,
    UNIQUE(regionName, dataDate)

Features:
- Reads parsed weather data from Task 2 (via weather_raw.json, no CWA API calls).
- Upserts records using INSERT ... ON CONFLICT to prevent duplicates across multiple runs.
- Executes required verification SQL queries:
    1. SELECT DISTINCT regionName FROM TemperatureForecasts;
    2. SELECT * FROM TemperatureForecasts WHERE regionName = '中部地區';
- Prints formatted verification and completeness checks for all 6 regions and 7-day forecasts.
"""

import os
import sys
import sqlite3
from collections import Counter

# 確保 Windows 主控台正確顯示 UTF-8 中文字元
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from parse_weather import (
    load_raw_json,
    aggregate_region_forecast,
    build_records,
    REGION_MAPPING,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data.db")
RAW_JSON_PATH = os.path.join(BASE_DIR, "weather_raw.json")


def get_connection(db_path=DB_PATH):
    """建立並回傳 SQLite 資料庫連線。"""
    return sqlite3.connect(db_path)


def init_db(conn):
    """
    建立 TemperatureForecasts 資料表與唯一索引（若不存在）。
    使用 UNIQUE(regionName, dataDate) 避免重複插入相同地區與日期的氣象資料。
    """
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS TemperatureForecasts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        regionName TEXT NOT NULL,
        dataDate TEXT NOT NULL,
        mint REAL NOT NULL,
        maxt REAL NOT NULL,
        UNIQUE(regionName, dataDate)
    );
    """
    cursor = conn.cursor()
    cursor.execute(create_table_sql)
    # 確保既有資料表也具備此唯一索引
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_region_date ON TemperatureForecasts(regionName, dataDate);"
    )
    conn.commit()


def save_forecasts(conn, records):
    """
    將天氣預報資料存入 TemperatureForecasts 資料表。
    使用 ON CONFLICT 更新現有記錄，確保重複執行時不產生重複資料。
    """
    insert_sql = """
    INSERT INTO TemperatureForecasts (regionName, dataDate, mint, maxt)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(regionName, dataDate) DO UPDATE SET
        mint = excluded.mint,
        maxt = excluded.maxt;
    """
    cursor = conn.cursor()
    payload = [
        (r["regionName"], r["dataDate"], float(r["mint"]), float(r["maxt"]))
        for r in records
    ]
    cursor.executemany(insert_sql, payload)
    conn.commit()
    return len(payload)


def run_verification_queries(conn):
    """
    執行作業規範要求的兩項 SQL 驗證查詢，並格式化輸出結果。
    """
    cursor = conn.cursor()

    # 驗證查詢 1: 列出所有地區名稱
    query1 = "SELECT DISTINCT regionName FROM TemperatureForecasts;"
    print("=" * 70)
    print("【SQL 驗證查詢 1】列出所有地區名稱")
    print(f"SQL: {query1}")
    print("=" * 70)
    cursor.execute(query1)
    distinct_regions = [row[0] for row in cursor.fetchall()]
    for idx, reg in enumerate(distinct_regions, 1):
        print(f"  [{idx}] {reg}")
    print(f"\n地區數量確認: {len(distinct_regions)} / 6 個地區")
    print("-" * 70)

    # 驗證查詢 2: 查詢中部地區資料
    query2 = "SELECT * FROM TemperatureForecasts WHERE regionName = '中部地區';"
    print("\n" + "=" * 70)
    print("【SQL 驗證查詢 2】查詢中部地區資料")
    print(f"SQL: {query2}")
    print("=" * 70)
    cursor.execute(query2)
    central_rows = cursor.fetchall()
    
    # 標題欄
    print(f"{'id':<5} {'regionName':<12} {'dataDate':<14} {'mint (MinT)':>12} {'maxt (MaxT)':>12}")
    print("-" * 60)
    for row in central_rows:
        row_id, r_name, d_date, mint, maxt = row
        print(f"{row_id:<5} {r_name:<12} {d_date:<14} {mint:>12.1f} {maxt:>12.1f}")
    print(f"\n中部地區資料筆數確認: {len(central_rows)} 筆預報")
    print("-" * 70)

    # 額外統計：驗證六大區域各預報天數與總筆數
    print("\n" + "=" * 70)
    print("【資料庫整體完整性檢查】各區域預報天數統計")
    print("=" * 70)
    cursor.execute("SELECT regionName, COUNT(*), MIN(dataDate), MAX(dataDate) FROM TemperatureForecasts GROUP BY regionName;")
    stats = cursor.fetchall()
    stats_dict = {row[0]: (row[1], row[2], row[3]) for row in stats}

    all_valid = True
    for region in REGION_MAPPING:
        if region in stats_dict:
            count, start_d, end_d = stats_dict[region]
            status = "OK" if count >= 7 else "WARN"
            if count < 7:
                all_valid = False
            print(f"  [{status}] {region:<10}: {count} 天 ({start_d} ~ {end_d})")
        else:
            all_valid = False
            print(f"  [MISSING] {region:<10}: 缺少資料！")

    cursor.execute("SELECT COUNT(*) FROM TemperatureForecasts;")
    total_count = cursor.fetchone()[0]
    print(f"\n總筆數: {total_count} 筆")
    if all_valid and len(distinct_regions) == 6:
        print(">> 驗證成功：六大區域完整儲存，各區域皆具備完整 7 天預報資料！")
    else:
        print(">> 驗證警告：部分資料或區域不完整，請檢查資料來源。")
    print("=" * 70)


def load_task2_records():
    """
    從 Task 2 的邏輯中載入已解析好的天氣預報資料。
    直接讀取 weather_raw.json，絕不重新呼叫 CWA API。
    """
    data = load_raw_json(RAW_JSON_PATH)
    locations = data["records"]["Locations"][0]["Location"]
    region_forecast = aggregate_region_forecast(locations)
    return build_records(region_forecast)


def main():
    print("=" * 70)
    print("【HW10 任務 3：存入 SQLite 資料庫 (data.db)】")
    print("=" * 70)
    print(f"1. 讀取 Task 2 解析資料 (來源: {os.path.basename(RAW_JSON_PATH)}) ...")
    records = load_task2_records()
    print(f"   成功取得 {len(records)} 筆預報紀錄。")

    print(f"\n2. 連線並初始化資料庫: {DB_PATH} ...")
    conn = get_connection(DB_PATH)
    try:
        init_db(conn)
        print("   資料表 TemperatureForecasts 與唯一性索引就緒。")

        print("\n3. 將氣象資料寫入 SQLite 資料庫 (支援冪等寫入防重複) ...")
        inserted_count = save_forecasts(conn, records)
        print(f"   已寫入 / 更新 {inserted_count} 筆預報紀錄至 data.db。")

        print("\n4. 執行 SQL 驗證查詢 ...\n")
        run_verification_queries(conn)
    finally:
        conn.close()

    print(f"\nTask 3 執行完成！資料庫檔案位置: {DB_PATH}")


if __name__ == "__main__":
    main()
