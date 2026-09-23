import sqlite3

# 連線到 SQLite 資料庫
conn = sqlite3.connect("data.db")

cursor = conn.cursor()

# 查詢南部地區的一週氣溫
cursor.execute("""
    SELECT regionName, dataDate, mint, maxt
    FROM TemperatureForecasts
    WHERE regionName = '南部地區'
    ORDER BY dataDate;
""")

# 取得查詢結果
rows = cursor.fetchall()

# 印出資料
for row in rows:
    print(row)

# 關閉資料庫連線
conn.close()