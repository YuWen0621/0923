# -*- coding: utf-8 -*-
"""
fetch_weather.py
================
[HW10 Task 1 & Stage 1] Fetch weather forecast JSON from CWA Open Data API.

Features:
- Reusable `fetch_cwa_forecast()` function for centralized update workflows.
- Safe fallback from F-A0010-001 to F-D0047-091 (7-day forecast dataset).
- Reads API key strictly from environment variables without exposing it.
- Configures UTF-8 output on Windows consoles to prevent character encoding errors.
"""

import os
import sys
import json
import urllib3
import requests
from dotenv import load_dotenv

# 確保 Windows 主控台正確顯示 UTF-8 中文字元
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 停用 SSL 警告（相容特定環境與憑證解析）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 載入 .env 檔案中的環境變數
load_dotenv()

DEFAULT_DATASET_ID = os.getenv("CWA_DATASET_ID", "F-D0047-091")


def get_api_key():
    """從環境變數讀取 CWA API 金鑰，不將金鑰寫死在程式碼中。"""
    return os.getenv("CWA_API_KEY")


def fetch_cwa_forecast(dataset_id=None, api_key=None, timeout=30):
    """
    可重用的 CWA API 請求函式。
    
    參數:
        dataset_id: 資料集識別代號，預設使用 F-D0047-091（現行一週天氣預報）。
        api_key: CWA API 授權碼，預設由環境變數 CWA_API_KEY 取得。
        timeout: 連線與讀取超時秒數，預設 30 秒。

    回傳:
        成功時回傳 CWA JSON 資料 (dict)；失敗時回傳 None 或拋出例外。
    """
    key = api_key or get_api_key()
    if not key:
        print("❌ 錯誤：未找到 CWA_API_KEY，請確認 .env 檔案中是否已設定。")
        return None

    target_dataset = dataset_id or DEFAULT_DATASET_ID
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{target_dataset}"
    headers = {"Authorization": key}

    try:
        resp = requests.get(url, headers=headers, timeout=timeout, verify=False)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success") == "true" or data.get("success") is True:
                return data
            else:
                print(f"⚠️ API 回應 200 但 success 欄位表示異常")
                return None
        elif resp.status_code == 404 and target_dataset == "F-A0010-001":
            # 若原始作業端點 404，自動備援切換現行一週預報端點 F-D0047-091
            print("🔄 F-A0010-001 回傳 404，自動切換至現行端點 F-D0047-091...")
            return fetch_cwa_forecast(dataset_id="F-D0047-091", api_key=key, timeout=timeout)
        else:
            print(f"❌ 請求失敗，狀態碼：{resp.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"❌ 連線發生錯誤：{e}")
        return None


def get_weather_data(dataset_id: str):
    """向下相容現有 Task 1 介面之函式別名。"""
    return fetch_cwa_forecast(dataset_id=dataset_id)


def main():
    print("=" * 60)
    print("【HW10 任務 1：取得 CWA API 資料】")
    print("=" * 60)

    dataset_to_try = os.getenv("CWA_DATASET_ID", "F-A0010-001")
    data = fetch_cwa_forecast(dataset_to_try)

    if data:
        print("✅ 任務 1 驗證完成：已成功取得天氣預報 JSON 資料！")
        raw_path = "weather_raw.json"
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"💾 原始 JSON 資料已儲存至：{raw_path}")
    else:
        print("❌ 任務 1 失敗：未能取得天氣資料，請檢查 API Key 或網路連線。")


if __name__ == "__main__":
    main()
