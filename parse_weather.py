# -*- coding: utf-8 -*-
"""
parse_weather.py
================
[HW10 Task 2 & Stage 2] Analyze JSON and extract 6-region weather & temperature forecast.

Data source: CWA F-D0047-091 (臺灣各縣市鄉鎮未來1週逐12小時天氣預報)

JSON hierarchy:
  data
  └── records
      └── Locations (list)
          └── [0]
              └── Location[] (22 counties/cities)
                  ├── LocationName
                  └── WeatherElement[]
                      ├── ElementName == "最高溫度" / "最低溫度"
                      ├── ElementName == "天氣現象" (Weather Description)
                      └── ElementName == "12小時降雨機率" (Probability of Precipitation)

Aggregation Rules for 6 Regions (六大分區聚合原則):
--------------------------------------------------
1. 最高溫 (MaxT):
   每縣市每日取白日時段 (06:00起) 之最高值；同區域內各縣市取平均值，保留一位小數。
2. 最低溫 (MinT):
   每縣市每日取各時段之最低值；同區域內各縣市取平均值，保留一位小數。
3. 天氣現象 (Weather Description):
   類別性文字（如「晴時多雲」、「多雲短暫雨」）不可進行數值平均。
   聚合規則：以該分區所屬各縣市白日時段出現頻率最高者（Mode 眾數）作為該分區當日之代表性天氣現象。
4. 降雨機率 (Probability of Precipitation - PoP):
   各縣市白日與夜間具備 12 小時降雨機率數值。
   聚合規則：計算該分區所有縣市當日有效降雨機率之平均值（四捨五入至整數百分比）；若遇無資料（如「-」）則排除不列入平均；若全區皆無數值則以 None 呈現。
"""

import json
import os
import sys
from collections import defaultdict, Counter

# 確保 Windows 主控台正確顯示 UTF-8 中文字元
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

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


def extract_weather_by_city(location):
    """
    從單一縣市 Location 提取每日最高溫、最低溫、天氣現象與降雨機率清單。

    回傳：
    {
        "YYYY-MM-DD": {
            "maxt": [int, ...],
            "mint": [int, ...],
            "weather": [str, ...],
            "pop": [int, ...]
        },
        ...
    }
    """
    daily = defaultdict(lambda: {"maxt": [], "mint": [], "weather": [], "pop": []})

    for element in location.get("WeatherElement", []):
        elem_name = element.get("ElementName", "")

        for time_slot in element.get("Time", []):
            start = time_slot.get("StartTime", "")
            date_str = start[:10]        # "YYYY-MM-DD"
            hour = int(start[11:13]) if len(start) >= 13 else 0

            values = time_slot.get("ElementValue", [{}])
            val_obj = values[0] if values else {}

            if elem_name == "最高溫度":
                raw_val = val_obj.get("MaxTemperature")
                if raw_val is not None and hour >= 6:
                    try:
                        daily[date_str]["maxt"].append(int(raw_val))
                    except ValueError:
                        pass
            elif elem_name == "最低溫度":
                raw_val = val_obj.get("MinTemperature")
                if raw_val is not None:
                    try:
                        daily[date_str]["mint"].append(int(raw_val))
                    except ValueError:
                        pass
            elif elem_name == "天氣現象":
                w = val_obj.get("Weather")
                if w:
                    daily[date_str]["weather"].append(w)
            elif elem_name == "12小時降雨機率":
                p = val_obj.get("ProbabilityOfPrecipitation")
                if p is not None and p.strip().isdigit():
                    daily[date_str]["pop"].append(int(p.strip()))

    return daily


def extract_temp_by_city(location):
    """向下相容現有 Task 2 函式名稱。"""
    city_data = extract_weather_by_city(location)
    # 僅回傳包含 maxt 與 mint 之結構以維持既有契約
    return {
        d: {"maxt": v["maxt"], "mint": v["mint"]}
        for d, v in city_data.items()
    }


def aggregate_region_forecast(locations):
    """
    將 22 縣市整合為六大區域的每日氣象預報 (MaxT, MinT, Weather, PoP)。

    邏輯：
      - 每縣市每日取 max(MaxT) 和 min(MinT)
      - 天氣現象取該分區各縣市出現頻率最高者（Mode 眾數）
      - 降雨機率取該分區各縣市之平均值（四捨五入整數百分比）
      - 同一區域的多縣市氣溫取平均（保留一位小數）
    """
    region_daily = defaultdict(lambda: defaultdict(lambda: {
        "maxt": [],
        "mint": [],
        "weather": [],
        "pop": [],
    }))

    for location in locations:
        city_name = location.get("LocationName", "")
        region = CITY_TO_REGION.get(city_name)
        if region is None:
            continue   # 金門縣、連江縣非六大分區，略過

        city_data = extract_weather_by_city(location)

        for date_str, data in city_data.items():
            if data["maxt"]:
                region_daily[region][date_str]["maxt"].append(max(data["maxt"]))
            if data["mint"]:
                region_daily[region][date_str]["mint"].append(min(data["mint"]))
            if data["weather"]:
                # 取該縣市當日最普遍之天氣描述
                city_wx = Counter(data["weather"]).most_common(1)[0][0]
                region_daily[region][date_str]["weather"].append(city_wx)
            if data["pop"]:
                # 縣市當日最高降雨機率代表該縣市當日降雨風險
                region_daily[region][date_str]["pop"].append(max(data["pop"]))

    result = {}
    for region in REGION_MAPPING:
        result[region] = {}
        if region not in region_daily:
            continue
        for date_str, agg in sorted(region_daily[region].items()):
            maxt_list = agg["maxt"]
            mint_list = agg["mint"]
            wx_list = agg["weather"]
            pop_list = agg["pop"]

            if maxt_list and mint_list:
                # 類別天氣現象：以區域內出現頻率最高者（Mode 眾數）為代表
                weather_desc = Counter(wx_list).most_common(1)[0][0] if wx_list else None
                # 降雨機率：區域代表值採各縣市有效 PoP 之平均值（四捨五入整數），若無資料則為 None
                pop_val = round(sum(pop_list) / len(pop_list)) if pop_list else None

                result[region][date_str] = {
                    "maxt": round(sum(maxt_list) / len(maxt_list), 1),
                    "mint": round(sum(mint_list) / len(mint_list), 1),
                    "weather": weather_desc,
                    "pop": pop_val,
                }

    return result


def build_records(region_forecast):
    """
    展平為 List[Dict]，包含氣溫與基礎天氣要素：
    regionName, dataDate, mint, maxt, weather, pop
    """
    records = []
    for region in REGION_MAPPING:
        for date_str, info in region_forecast.get(region, {}).items():
            records.append({
                "regionName": region,
                "dataDate":   date_str,
                "mint":       info["mint"],
                "maxt":       info["maxt"],
                "weather":    info.get("weather"),
                "pop":        info.get("pop"),
            })
    return records


def parse_cwa_json(data):
    """
    純記憶體解析 CWA JSON 物件，不依賴本機磁碟檔案。
    適用於即時更新管線與未來 Vercel / API 服務。
    """
    try:
        locations = data["records"]["Locations"][0]["Location"]
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError(f"Invalid CWA JSON structure: {e}")

    region_forecast = aggregate_region_forecast(locations)
    return build_records(region_forecast)


def print_results(records):
    """列印提取結果並驗證六區完整性。"""
    print("=" * 75)
    print("【HW10 任務 2：分析 JSON，提取氣溫與天氣資料】")
    print("=" * 75)
    print(f"{'regionName':<10} {'dataDate':<12} {'MinT':>6} {'MaxT':>6} {'PoP':>6}  {'天氣現象'}")
    print("-" * 65)

    current_region = None
    for rec in records:
        if rec["regionName"] != current_region:
            if current_region is not None:
                print()
            current_region = rec["regionName"]
        pop_str = f"{rec['pop']}%" if rec.get("pop") is not None else "--"
        wx_str = rec.get("weather") or "--"
        print(f"{rec['regionName']:<10} {rec['dataDate']:<12} {rec['mint']:>6.1f} {rec['maxt']:>6.1f} {pop_str:>6}  {wx_str}")

    print("\n" + "=" * 75)
    print("驗證摘要")
    print("=" * 75)
    region_counts = Counter(r["regionName"] for r in records)
    all_ok = True

    for region in REGION_MAPPING:
        count = region_counts.get(region, 0)
        status = "OK" if count >= 7 else "WARN"
        if count < 7:
            all_ok = False
        print(f"  [{status}]  {region:<10}  {count} 筆資料")

    print()
    if all_ok:
        print("六大區域均已擷取，各含 7 天預報資料與基礎天氣資訊！")
    else:
        print("部分區域資料不足 7 天，請確認 API 回傳完整度。")
    print("=" * 75)


def main():
    print("=" * 75)
    print("正在讀取 weather_raw.json ...")

    data = load_raw_json("weather_raw.json")
    records = parse_cwa_json(data)

    print(f"   成功提取 {len(records)} 筆預報紀錄 (6 regions x ~7 days)")
    print()
    print_results(records)
    return records


if __name__ == "__main__":
    main()
