"""
check_db.py — 快速檢視 ChromaDB 中的書籍資訊
用法：python check_db.py
"""
import chromadb
from collections import Counter

# 改成你實際的持久化路徑
PERSIST_DIR = "./chroma_db"

client = chromadb.PersistentClient(path=PERSIST_DIR)

for collection in client.list_collections():
    print(f"\n{'='*60}")
    print(f"📂 Collection: {collection.name}")
    print(f"{'='*60}")
    
    data = collection.get(include=["metadatas"])
    ids = data["ids"]
    metadatas = data["metadatas"]
    
    print(f"總文件片段數: {len(ids)}")
    
    # 統計每本書的片段數
    book_counts = Counter()
    for meta in metadatas:
        source = meta.get("source") or meta.get("title") or meta.get("file_name") or "未知"
        # 只取檔名
        clean_name = str(source).split("/")[-1].split("\\")[-1]
        book_counts[clean_name] += 1
    
    print(f"\n書籍清單 ({len(book_counts)} 本):")
    print(f"{'─'*50}")
    for book, count in book_counts.most_common():
        print(f"  📖 {book}  →  {count} 個片段")
    print(f"{'─'*50}")