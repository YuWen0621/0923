# -*- coding: utf-8 -*-
"""
parse_weather.py
================
[HW10 Task 2] Analyze JSON and extract 6-region weekly temperature forecast.

Data source: weather_raw.json (produced by fetch_weather.py from CWA F-D0047-091)

JSON hierarchy:
  data
  └── records
      └── Locations (list)
          └── [0]
              └── Location[] (22 counties/cities)
                  ├── LocationName
                  └── WeatherElement[]
                      └── ElementName == "最高溫度" / "最低溫度"
                          └── Time[]
                              ├── StartTime
                              └── ElementValue
                                  └── MaxTemperature / MinTemperature
"""

import json
import os
from collections import defaultdict, Counter

# =============================================================
# 六大區域與縣市對照表
# =============================================================
REGION_MAPPING = {
    "北部地區":   ["臺北市", "新北市", "基隆市", "桃園市", "新竹市", "新竹縣"],
    "中部地區":   ["臺中市", "苗栗縣", "彰化縣", "南投縣", "雲林縣"],
    "南部地區":   ["臺南市", "高雄市", "嘉義市", "嘉義縣", "屏東縣", "澎湖縣"],
    "東北部地區": ["宜蘭縣"],
    "東部地區":   ["花蓮縣"],
    "東南部地區": ["臺東縣"],
}

# 縣市 → 所屬地區反查表
CITY_TO_REGION = {}
for _region, _cities in REGION_MAPPING.items():
    for _city in _cities:
        CITY_TO_REGION[_city] = _region


def load_raw_json(filepath="weather_raw.json"):
    """讀取 weather_raw.json；若不存在給出明確錯誤訊息。"""
    if not os.path.exists(filepath):
        raise FileNotFoundError(
            f"[ERROR] Cannot find {filepath}!\n"
            "Please run fetch_weather.py first:\n"
            "  python fetch_weather.py"
        )
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_temp_by_city(location):
    """
    從單一縣市 Location 提取每日溫度清單。

    回傳：
    {
        "YYYY-MM-DD": {"maxt": [int,...], "mint": [int,...]},
        ...
    }
    """
    daily = defaultdict(lambda: {"maxt": [], "mint": []})

    for element in location.get("WeatherElement", []):
        elem_name = element.get("ElementName", "")

        if elem_name == "最高溫度":
            key = "maxt"
            val_field = "MaxTemperature"
        elif elem_name == "最低溫度":
            key = "mint"
            val_field = "MinTemperature"
        else:
            continue

        for time_slot in element.get("Time", []):
            start = time_slot.get("StartTime", "")
            date_str = start[:10]        # "YYYY-MM-DD"
            hour = int(start[11:13])     # 時

            values = time_slot.get("ElementValue", [{}])
            raw_val = values[0].get(val_field)
            if raw_val is None:
                continue
            try:
                temp = int(raw_val)
            except ValueError:
                continue

            # MaxT 只採白天 (06:00 起始) 時段，避免夜間偏低值干擾最高溫
            if key == "maxt" and hour < 6:
                continue

            daily[date_str][key].append(temp)

    return daily


def aggregate_region_forecast(locations):
    """
    將 22 縣市整合為六大區域的每日 MaxT/MinT。

    邏輯：
      - 每縣市每日取 max(MaxT時段) 和 min(MinT時段)
      - 同一區域的多縣市取平均（四捨五入）

    回傳：
    {
        "北部地區": {
            "YYYY-MM-DD": {"maxt": int, "mint": int},
            ...
        },
        ...
    }
    """
    # region -> date -> {"maxt": [city_val,...], "mint": [city_val,...]}
    region_daily = defaultdict(lambda: defaultdict(lambda: {"maxt": [], "mint": []}))

    for location in locations:
        city_name = location.get("LocationName", "")
        region = CITY_TO_REGION.get(city_name)
        if region is None:
            continue   # 連江縣、金門縣不在六大區，略過

        city_temps = extract_temp_by_city(location)

        for date_str, temps in city_temps.items():
            if temps["maxt"]:
                region_daily[region][date_str]["maxt"].append(max(temps["maxt"]))
            if temps["mint"]:
                region_daily[region][date_str]["mint"].append(min(temps["mint"]))

    # 跨縣市取平均
    result = {}
    for region in REGION_MAPPING:
        result[region] = {}
        if region not in region_daily:
            continue
        for date_str, agg in sorted(region_daily[region].items()):
            maxt_list = agg["maxt"]
            mint_list = agg["mint"]
            if maxt_list and mint_list:
                result[region][date_str] = {
                    "maxt": round(sum(maxt_list) / len(maxt_list)),
                    "mint": round(sum(mint_list) / len(mint_list)),
                }

    return result


def build_records(region_forecast):
    """
    展平為 List[Dict]，對應 Task 3 資料表欄位：
    regionName, dataDate, mint, maxt
    """
    records = []
    for region in REGION_MAPPING:
        for date_str, temps in region_forecast.get(region, {}).items():
            records.append({
                "regionName": region,
                "dataDate":   date_str,
                "mint":       temps["mint"],
                "maxt":       temps["maxt"],
            })
    return records


def print_results(records):
    """列印提取結果並驗證六區完整性。"""
    print("=" * 65)
    print("【HW10 任務 2：分析 JSON，提取氣溫資料】")
    print("=" * 65)
    print(f"{'regionName':<12}  {'dataDate':<12}  {'MinT':>5}  {'MaxT':>5}")
    print("-" * 45)

    current_region = None
    for rec in records:
        if rec["regionName"] != current_region:
            if current_region is not None:
                print()
            current_region = rec["regionName"]
        print(f"{rec['regionName']:<12}  {rec['dataDate']:<12}  {rec['mint']:>5}  {rec['maxt']:>5}")

    # --- Validation ---
    print("\n" + "=" * 65)
    print("驗證摘要")
    print("=" * 65)
    region_counts = Counter(r["regionName"] for r in records)
    all_ok = True

    for region in REGION_MAPPING:
        count = region_counts.get(region, 0)
        status = "OK" if count >= 7 else "WARN"
        if count < 7:
            all_ok = False
        print(f"  [{status}]  {region:<12}  {count} 筆資料")

    print()
    if all_ok:
        print("六大區域均已擷取，各含 7 天以上預報資料！")
    else:
        print("部分區域資料不足 7 天，請確認 API 回傳完整度。")
    print("=" * 65)


def main():
    print("=" * 65)
    print("正在讀取 weather_raw.json ...")

    # Step 1: Load raw JSON
    data = load_raw_json("weather_raw.json")

    # Step 2: Navigate JSON hierarchy to get 22-city Location list
    #   Path: data["records"]["Locations"][0]["Location"]
    try:
        locations = data["records"]["Locations"][0]["Location"]
    except (KeyError, IndexError) as e:
        print(f"JSON structure error: {e}")
        return

    print(f"   Loaded {len(locations)} city/county locations")

    # Step 3: Aggregate into 6-region daily forecast
    region_forecast = aggregate_region_forecast(locations)

    # Step 4: Flatten to list of dicts
    records = build_records(region_forecast)

    print(f"   Extracted {len(records)} forecast records (6 regions x ~7 days)")
    print()

    # Step 5: Print results
    print_results(records)

    return records   # Task 3 can import and call main()


if __name__ == "__main__":
    main()
