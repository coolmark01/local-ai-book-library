# -*- coding: utf-8 -*-
"""
書籍目錄掃描與清單管理模組 (catalog_manager.py)
==============================================
負責：
  1. 遞迴遍歷指定本機目錄及其子資料夾，收集所有支援格式書籍 (PDF, EPUB, TXT)
  2. 檔案路徑去重 (De-duplication) 與本地持久化 (book_catalog.json)
  3. 即時與 ChromaDB 向量資料庫比對入庫狀態 (已匯入 / 未匯入)
  4. 支援路徑校驗與清單維護
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Set, Tuple

logger = logging.getLogger("LibraryLogger")

CATALOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "book_catalog.json")
SUPPORTED_EXTENSIONS = {".pdf", ".epub", ".txt"}


class CatalogManager:
    """本機書籍總清單管理器"""

    @staticmethod
    def load_catalog() -> Dict[str, Dict[str, Any]]:
        """讀取本地掃描清單快取。"""
        if os.path.exists(CATALOG_FILE):
            try:
                with open(CATALOG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"[Catalog] 讀取書籍清單失敗: {e}")
        return {}

    @staticmethod
    def save_catalog(catalog: Dict[str, Dict[str, Any]]):
        """將書籍總清單保存至本地 JSON 檔案。"""
        try:
            with open(CATALOG_FILE, "w", encoding="utf-8") as f:
                json.dump(catalog, f, ensure_ascii=False, indent=2)
            logger.info(f"[Catalog] 已保存 {len(catalog)} 本書籍記錄至清單。")
        except Exception as e:
            logger.error(f"[Catalog] 保存書籍清單失敗: {e}")

    @classmethod
    def scan_directory(
        cls,
        root_dir: str,
        existing_catalog: Dict[str, Dict[str, Any]] = None
    ) -> Tuple[Dict[str, Dict[str, Any]], int, int]:
        """
        遞迴掃描目錄與子資料夾。
        回傳: (更新後的清單, 新增書籍數, 目前總書籍數)
        """
        if existing_catalog is None:
            existing_catalog = cls.load_catalog()

        normalized_root = os.path.abspath(os.path.expanduser(root_dir))
        if not os.path.isdir(normalized_root):
            raise ValueError(f"指定的路徑不存在或非資料夾: {root_dir}")

        new_count = 0
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for dirpath, _, filenames in os.walk(normalized_root):
            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                if ext in SUPPORTED_EXTENSIONS:
                    full_path = os.path.abspath(os.path.join(dirpath, fname))
                    
                    # 檔案唯一識別鍵（規範化路徑）
                    if full_path not in existing_catalog:
                        try:
                            file_size_mb = round(os.path.getsize(full_path) / (1024 * 1024), 2)
                        except Exception:
                            file_size_mb = 0.0

                        existing_catalog[full_path] = {
                            "filename": fname,
                            "file_path": full_path,
                            "folder": os.path.relpath(dirpath, normalized_root),
                            "file_type": ext.replace(".", "").upper(),
                            "file_size_mb": file_size_mb,
                            "scanned_at": now_str,
                            "is_imported": False,
                            "imported_at": None,
                            "chunk_count": 0
                        }
                        new_count += 1
                    else:
                        # 若已存在，僅更新檔案大小或存在狀態
                        if os.path.exists(full_path):
                            try:
                                existing_catalog[full_path]["file_size_mb"] = round(os.path.getsize(full_path) / (1024 * 1024), 2)
                            except Exception:
                                pass

        cls.save_catalog(existing_catalog)
        return existing_catalog, new_count, len(existing_catalog)

    @classmethod
    def sync_with_database(
        cls,
        catalog: Dict[str, Dict[str, Any]],
        db_books: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        即時比對向量資料庫中的書籍，動態校正 is_imported 狀態。
        若從向量庫刪除，此處自動同步恢復為未匯入。
        """
        # 建立資料庫中現存書籍的識別集合 (包含 filename 與 source 路徑)
        active_sources = {}
        for b in db_books:
            src = b.get("source", "")
            fname = b.get("filename", "")
            count = b.get("chunk_count", 0)
            if src:
                active_sources[src] = count
            if fname:
                active_sources[fname] = count

        for path, info in catalog.items():
            fname = info.get("filename", "")
            # 只要資料庫中存在該檔名或路徑，且片段數 > 0，即為已匯入
            if path in active_sources and active_sources[path] > 0:
                info["is_imported"] = True
                info["chunk_count"] = active_sources[path]
            elif fname in active_sources and active_sources[fname] > 0:
                info["is_imported"] = True
                info["chunk_count"] = active_sources[fname]
            else:
                info["is_imported"] = False
                info["chunk_count"] = 0

        cls.save_catalog(catalog)
        return catalog

    @classmethod
    def remove_item(cls, file_path: str, catalog: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """從總清單中移除指定書籍記錄。"""
        if file_path in catalog:
            del catalog[file_path]
            cls.save_catalog(catalog)
        return catalog

    @classmethod
    def clean_missing_files(cls, catalog: Dict[str, Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], int]:
        """清除磁碟上已經不存在的遺失檔案記錄。"""
        missing_paths = [p for p in catalog.keys() if not os.path.exists(p)]
        for p in missing_paths:
            del catalog[p]
        if missing_paths:
            cls.save_catalog(catalog)
        return catalog, len(missing_paths)