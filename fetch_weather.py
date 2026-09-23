import os
import json
import requests
import urllib3
from dotenv import load_dotenv

# 停用 SSL 警告（相容特定環境與憑證解析）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 載入 .env 檔案中的環境變數
load_dotenv()

# 從環境變數讀取 CWA API 金鑰，不將金鑰寫死在程式碼中
API_KEY = os.getenv("CWA_API_KEY")
DATASET_ID = os.getenv("CWA_DATASET_ID", "F-A0010-001")


def get_weather_data(dataset_id: str):
    """使用 requests 呼叫中央氣象署 (CWA) Open Data API 取得天氣預報 JSON 資料"""
    if not API_KEY:
        print("❌ 錯誤：未找到 CWA_API_KEY，請確認 .env 檔案中是否已設定。")
        return None

    # CWA RESTful Datastore API 端點
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{dataset_id}"
    headers = {
        "Authorization": API_KEY
    }

    print(f"📡 正在請求中央氣象署 Open Data API (資料集: {dataset_id})...")
    print(f"🔗 請求網址: {url}")

    try:
        # 發送 GET 請求，加入 timeout 避免無限等待，並設置 verify=False 避免憑證錯誤
        resp = requests.get(url, headers=headers, timeout=30, verify=False)

        # 檢查請求狀態碼
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success") == "true" or data.get("success") is True:
                print(f"✅ 資料取得成功！(狀態碼: {resp.status_code})")
                return data
            else:
                print(f"⚠️ API 呼叫回傳 200，但資料內容表示失敗: {data}")
                return data
        else:
            print(f"❌ 請求失敗，狀態碼：{resp.status_code}")
            try:
                err_data = resp.json()
                print(f"伺服器回應：{err_data}")
            except Exception:
                print(f"伺服器回應：{resp.text}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"❌ 連線發生錯誤：{e}")
        return None


def main():
    print("=" * 60)
    print("【HW10 任務 1：取得 CWA API 資料】")
    print("=" * 60)

    # 1. 嘗試呼叫作業指定的資料集 F-A0010-001
    data = get_weather_data(DATASET_ID)

    # 2. 若 F-A0010-001 遇氣象署伺服器 404 (因官方平臺改版調整)，自動使用現行一週天氣預報資料集 (F-D0047-091)
    if not data and DATASET_ID == "F-A0010-001":
        print("\n💡 說明：中央氣象署官方平臺近期調整，原 F-A0010-001 端點回傳 404 (Resource not found)。")
        print("🔄 自動切換至氣象署現行一週天氣預報資料集 (F-D0047-091) 進行取得...")
        data = get_weather_data("F-D0047-091")

    # 3. 輸出回傳之 JSON 資料以供觀察結構
    if data:
        print("\n" + "=" * 60)
        print("🔍 回傳的 JSON 資料結構 (使用 json.dumps 格式化)：")
        print("=" * 60)
        formatted_json = json.dumps(data, indent=2, ensure_ascii=False)
        print(formatted_json)
        print("\n" + "=" * 60)
        print("✅ 任務 1 驗證完成：已成功取得並顯示天氣預報 JSON 資料！")
        print("=" * 60)
    else:
        print("\n❌ 任務 1 失敗：未能取得天氣資料，請檢查 API Key 或網路連線。")


if __name__ == "__main__":
    main()
