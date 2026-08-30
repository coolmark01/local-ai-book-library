import sqlite3
import os

db_path = "chroma_db/chroma.sqlite3"  # 請改成你實際的資料庫路徑

# 1. 先關閉 ChromaDB 連線（停止 Streamlit）
# 2. 執行 VACUUM
conn = sqlite3.connect(db_path)
conn.execute("VACUUM")
conn.close()

# 3. 確認檔案大小
size_mb = os.path.getsize(db_path) / (1024 * 1024)
print(f"壓縮後大小: {size_mb:.1f} MB")