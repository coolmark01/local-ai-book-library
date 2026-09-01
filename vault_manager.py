# -*- coding: utf-8 -*-
"""
第二大腦筆記庫管理器 (vault_manager.py)
======================================
負責：
  1. 永久保存各模組產出的 Markdown 筆記至本地 Vault (vault_notes/)
  2. 自動注入標準 YAML Frontmatter 元數據 (Title, Tags, Sources, Created Date)
  3. 支援筆記索引讀取、全文搜尋、標籤聚合、下載與刪除
  4. 支援自訂本機 Obsidian Vault 同步目錄
"""

import os
import re
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("LibraryLogger")

VAULT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vault_notes")
VAULT_META_FILE = os.path.join(VAULT_DIR, "_vault_index.json")


class VaultManager:
    """第二大腦筆記管理引擎"""

    @classmethod
    def _ensure_dir(cls):
        """確保筆記庫目錄存在。"""
        if not os.path.exists(VAULT_DIR):
            os.makedirs(VAULT_DIR, exist_ok=True)

    @classmethod
    def sanitize_filename(cls, title: str) -> str:
        """過濾檔名非法字元。"""
        cleaned = re.sub(r'[\\/*?:"<>|#\[\]]', '', title).strip()
        return cleaned[:80] if cleaned else f"Note_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    @classmethod
    def save_note(
        cls,
        title: str,
        content: str,
        note_type: str = "general",
        source_books: Optional[List[str]] = None,
        tags: Optional[List[str]] = None
    ) -> Tuple[bool, str, str]:
        """
        儲存 Markdown 筆記至第二大腦資料庫。
        回傳: (成功與否, 提示訊息, 檔案路徑)
        """
        cls._ensure_dir()
        source_books = source_books or []
        tags = tags or ["#SecondBrain"]

        safe_title = cls.sanitize_filename(title)
        file_name = f"{safe_title}.md"
        file_path = os.path.join(VAULT_DIR, file_name)

        # 檔名重複防衝突：加上序號
        counter = 1
        base_title = safe_title
        while os.path.exists(file_path):
            # 若檔案已存在且內容一致，直接視為已存在
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    if f.read().strip() == content.strip():
                        return True, "筆記已在第二大腦庫中（內容完全一致）", file_path
            except Exception:
                pass
            safe_title = f"{base_title}_{counter}"
            file_name = f"{safe_title}.md"
            file_path = os.path.join(VAULT_DIR, file_name)
            counter += 1

        # 若筆記原本沒有 YAML Frontmatter，自動注入標準頭部
        final_content = content
        if not content.startswith("---"):
            tags_yaml = "\n".join([f"  - {t}" for t in tags])
            sources_yaml = "\n".join([f'  - "[[{b}]]"' for b in source_books]) if source_books else '  - "[[AI Library]]"'
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            yaml_header = f"""---
title: "[[{safe_title}]]"
created_at: {now_str}
updated_at: {now_str}
type: {note_type}
sources:
{sources_yaml}
tags:
{tags_yaml}
---

"""
            final_content = yaml_header + content

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(final_content)
            
            logger.info(f"[Vault] 筆記成功存入第二大腦: {file_name}")
            return True, f"已成功存入第二大腦：{file_name}", file_path
        except Exception as e:
            logger.error(f"[Vault] 筆記儲存失敗: {e}", exc_info=True)
            return False, f"儲存失敗：{e}", ""

    @classmethod
    def list_notes(cls) -> List[Dict[str, Any]]:
        """列出第二大腦資料夾中的所有筆記與其元數據。"""
        cls._ensure_dir()
        notes = []

        if not os.path.exists(VAULT_DIR):
            return []

        for fname in os.listdir(VAULT_DIR):
            if fname.endswith(".md") and not fname.startswith("_"):
                fpath = os.path.join(VAULT_DIR, fname)
                try:
                    stats = os.stat(fpath)
                    modified_at = datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%d %H:%M")
                    
                    with open(fpath, "r", encoding="utf-8") as f:
                        raw_text = f.read()

                    # 簡易解析 YAML 元數據
                    note_type = "未分類"
                    sources = []
                    tags = []
                    
                    if raw_text.startswith("---"):
                        parts = raw_text.split("---", 2)
                        if len(parts) >= 3:
                            yaml_part = parts[1]
                            type_match = re.search(r'type:\s*([^\n]+)', yaml_part)
                            if type_match:
                                note_type = type_match.group(1).strip()
                            
                            tags_match = re.findall(r'-\s*(#[^\s\n]+)', yaml_part)
                            if tags_match:
                                tags = tags_match

                            sources_match = re.findall(r'\[\[(.*?)\]\]', yaml_part)
                            if sources_match:
                                sources = [s for s in sources_match if s != fname.replace(".md", "")]

                    # 計算內文字數 (排除 YAML)
                    body_text = raw_text.split("---", 2)[-1] if raw_text.startswith("---") else raw_text
                    word_count = len(body_text.strip())

                    notes.append({
                        "filename": fname,
                        "title": fname[:-3],
                        "file_path": fpath,
                        "note_type": note_type,
                        "sources": sources,
                        "tags": tags,
                        "word_count": word_count,
                        "modified_at": modified_at,
                        "content": raw_text
                    })
                except Exception as e:
                    logger.warning(f"[Vault] 讀取筆記失敗 {fname}: {e}")

        # 依最後修改時間降序排列 (最新在前)
        notes.sort(key=lambda x: x["modified_at"], reverse=True)
        return notes

    @classmethod
    def get_note_content(cls, filename: str) -> Optional[str]:
        """讀取單一筆記內容。"""
        fpath = os.path.join(VAULT_DIR, filename)
        if os.path.exists(fpath):
            with open(fpath, "r", encoding="utf-8") as f:
                return f.read()
        return None

    @classmethod
    def delete_note(cls, filename: str) -> Tuple[bool, str]:
        """從第二大腦中刪除特定筆記。"""
        fpath = os.path.join(VAULT_DIR, filename)
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
                logger.info(f"[Vault] 筆記已刪除: {filename}")
                return True, f"已成功刪除筆記《{filename}》"
            except Exception as e:
                return False, f"刪除失敗：{e}"
        return False, "找不到指定筆記"

    @classmethod
    def export_all_as_zip(cls) -> Optional[bytes]:
        """將所有筆記打包為 ZIP 下載檔。"""
        import io
        import zipfile
        cls._ensure_dir()
        
        notes = [f for f in os.listdir(VAULT_DIR) if f.endswith(".md")]
        if not notes:
            return None

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for fname in notes:
                fpath = os.path.join(VAULT_DIR, fname)
                zf.write(fpath, arcname=fname)

        zip_buffer.seek(0)
        return zip_buffer.getvalue()