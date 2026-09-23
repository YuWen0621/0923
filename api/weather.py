# -*- coding: utf-8 -*-
"""
api/weather.py
==============
Vercel Serverless Function (Python) for Taiwan Weather Forecast API.
Reuses fetch_weather.py and parse_weather.py without requiring SQLite writes.
"""

from http.server import BaseHTTPRequestHandler
import json
import os
import sys
import urllib.parse
from datetime import datetime, timezone, timedelta

# Ensure root directory is in sys.path to import existing modules
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

try:
    from zoneinfo import ZoneInfo
    TAIPEI_TZ = ZoneInfo("Asia/Taipei")
except Exception:
    TAIPEI_TZ = timezone(timedelta(hours=8))

import fetch_weather
import parse_weather

# In-memory cache for warm serverless instances
_cache = {
    "data": None,
    "last_fetched_dt": None,
    "last_fetched_display": None,
}
CACHE_TTL_SECONDS = 6 * 3600  # 6 hours


def format_forecast_response(records, last_fetch_display, is_cached=False):
    """Formats flat records from parse_weather into structured JSON."""
    now_taipei = datetime.now(TAIPEI_TZ).strftime("%Y-%m-%d %H:%M")
    
    dates_set = set()
    regions_dict = {}
    
    for r in records:
        r_name = r["regionName"]
        d_date = r["dataDate"]
        dates_set.add(d_date)
        
        if r_name not in regions_dict:
            regions_dict[r_name] = []
            
        mint = float(r["mint"])
        maxt = float(r["maxt"])
        avg_temp = round((mint + maxt) / 2.0, 1)
        
        regions_dict[r_name].append({
            "date": d_date,
            "mint": mint,
            "maxt": maxt,
            "avg": avg_temp,
            "weather": r.get("weather") or "--",
            "pop": r.get("pop"),
        })
    
    # Sort dates and region forecasts chronologically
    sorted_dates = sorted(list(dates_set))
    for r_name in regions_dict:
        regions_dict[r_name].sort(key=lambda x: x["date"])
        
    return {
        "success": True,
        "meta": {
            "now_display": now_taipei,
            "last_fetch_display": last_fetch_display,
            "interval_hours": 6,
            "is_cached": is_cached,
        },
        "dates": sorted_dates,
        "regions": regions_dict,
    }


def get_weather_data(force=False):
    """Fetches and parses weather data, utilizing in-memory cache and fallbacks."""
    global _cache
    now = datetime.now(TAIPEI_TZ)
    
    # Check cache if not forcing refresh
    if not force and _cache["data"] and _cache["last_fetched_dt"]:
        age = (now - _cache["last_fetched_dt"]).total_seconds()
        if age < CACHE_TTL_SECONDS:
            return format_forecast_response(
                _cache["data"], 
                _cache["last_fetched_display"], 
                is_cached=True
            )
    
    raw_json = None
    fetch_success = False
    
    # Attempt to fetch live data from CWA
    try:
        raw_json = fetch_weather.fetch_cwa_forecast(timeout=25)
        if raw_json and (raw_json.get("success") == "true" or raw_json.get("success") is True):
            fetch_success = True
    except Exception as e:
        print(f"Live fetch error: {e}", file=sys.stderr)
        
    # If live fetch failed, fallback to in-memory cache or local weather_raw.json
    if not fetch_success or not raw_json:
        if _cache["data"]:
            return format_forecast_response(
                _cache["data"], 
                _cache["last_fetched_display"], 
                is_cached=True
            )
        
        # Cold start fallback: local weather_raw.json
        raw_path = os.path.join(ROOT_DIR, "weather_raw.json")
        if os.path.exists(raw_path):
            try:
                with open(raw_path, "r", encoding="utf-8") as f:
                    raw_json = json.load(f)
            except Exception as e:
                print(f"Fallback json load error: {e}", file=sys.stderr)

    if not raw_json:
        return {
            "success": False,
            "error": "無法取得中央氣象署氣象資料，請確認 API Key 與網路連線。",
        }

    try:
        records = parse_weather.parse_cwa_json(raw_json)
        fetch_display = now.strftime("%Y-%m-%d %H:%M")
        
        # Update cache
        _cache["data"] = records
        _cache["last_fetched_dt"] = now
        _cache["last_fetched_display"] = fetch_display
        
        return format_forecast_response(records, fetch_display, is_cached=False)
    except Exception as e:
        if _cache["data"]:
            return format_forecast_response(
                _cache["data"], 
                _cache["last_fetched_display"], 
                is_cached=True
            )
        return {
            "success": False,
            "error": f"解析資料時發生錯誤：{str(e)}",
        }


class handler(BaseHTTPRequestHandler):
    """Vercel Python serverless HTTP request handler."""
    
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        force = params.get("force", ["0"])[0] in ("1", "true", "True")
        
        try:
            data = get_weather_data(force=force)
            status_code = 200 if data.get("success") else 500
        except Exception as e:
            data = {"success": False, "error": str(e)}
            status_code = 500
            
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        
        # Cache control: if force or error, no-cache; else allow short CDN cache
        if force or not data.get("success"):
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        else:
            self.send_header("Cache-Control", "public, s-maxage=3600, stale-while-revalidate=86400")
            
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()
