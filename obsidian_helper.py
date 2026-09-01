# -*- coding: utf-8 -*-
"""
Obsidian 與第二大腦共用輔助元件 (obsidian_helper.py)
===================================================
提供：
  1. render_clipboard_and_download_bar (標準第二大腦操作列：存入/複製/下載，含自動唯一 Key 防衝突機制)
  2. render_obsidian_button (向下完全相容 engine, content, docs 等舊版參數)
  3. _render_copy_button / render_copy_button (剪貼簿複製元件)
"""

import os
import re
import json
import hashlib
from typing import Optional, List, Any
import streamlit as st
import streamlit.components.v1 as components
from vault_manager import VaultManager


# ===================================================================
# 輔助：計算內容唯一哈希 (防 Streamlit Duplicate Key 衝突)
# ===================================================================
def _generate_unique_key(base_prefix: str, content: str, filename: str, **kwargs) -> str:
    """自動產生唯一的 Element Key，防止迴圈重複渲染時發生 Key 衝突。"""
    custom_key = kwargs.get("key") or kwargs.get("button_id") or kwargs.get("idx")
    if custom_key:
        safe_custom = "".join(c for c in str(custom_key) if c.isalnum() or c == "_")
        return f"{base_prefix}_{safe_custom}"

    # 若未指定自訂 key，使用檔案名稱與內容特徵計算 MD5 短哈希
    sample_text = f"{filename}_{len(content)}_{content[:120] if content else ''}"
    short_hash = hashlib.md5(sample_text.encode("utf-8", errors="ignore")).hexdigest()[:8]
    return f"{base_prefix}_{short_hash}"


# ===================================================================
# 輔助：跨版本 Streamlit HTML 渲染器
# ===================================================================
def _safe_html_render(html_content: str, height: int = 45):
    """相容新版 st.html 與舊版 st.components.v1.html。"""
    try:
        if hasattr(st, "html"):
            st.html(html_content)
        else:
            components.html(html_content, height=height)
    except Exception:
        components.html(html_content, height=height)


# ===================================================================
# 1. 剪貼簿獨立複製元件
# ===================================================================
def _render_copy_button(
    text: str = "",
    key_prefix: str = "cp",
    button_id: Optional[str] = None,
    **kwargs
):
    """渲染瀏覽器原生剪貼簿複製按鈕。"""
    content = text or kwargs.get("content", "")
    unique_key = _generate_unique_key(key_prefix, content, button_id or "btn", **kwargs)
    safe_dom_id = "".join(c for c in unique_key if c.isalnum() or c == "_") or "copyBtn"

    escaped_content = json.dumps(content)
    copy_html = f"""
    <button id="copyBtn_{safe_dom_id}" style="
        width: 100%;
        height: 38px;
        background-color: #2b2b36;
        color: #ffffff;
        border: 1px solid #4a4a5a;
        border-radius: 6px;
        font-size: 14px;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 6px;
        transition: all 0.2s;
    " onmouseover="this.style.backgroundColor='#3b3b4d'" onmouseout="this.style.backgroundColor='#2b2b36'">
        📋 複製內容
    </button>
    <script>
    document.getElementById("copyBtn_{safe_dom_id}").addEventListener("click", function() {{
        const text = {escaped_content};
        navigator.clipboard.writeText(text).then(function() {{
            const btn = document.getElementById("copyBtn_{safe_dom_id}");
            const originalText = btn.innerText;
            btn.innerText = "✅ 已複製！";
            btn.style.backgroundColor = "#238636";
            btn.style.borderColor = "#2ea043";
            setTimeout(function() {{
                btn.innerText = originalText;
                btn.style.backgroundColor = "#2b2b36";
                btn.style.borderColor = "#4a4a5a";
            }}, 2000);
        }}).catch(function(err) {{
            alert("複製失敗，請手動反白選取內容。");
        }});
    }});
    </script>
    """
    _safe_html_render(copy_html, height=45)


def render_copy_button(text: str = "", key_prefix: str = "cp", button_id: Optional[str] = None, **kwargs):
    """公開別名相容。"""
    _render_copy_button(text=text, key_prefix=key_prefix, button_id=button_id, **kwargs)


# ===================================================================
# 2. 第二大腦標準操作列 (存入第二大腦 + 複製 + 下載)
# ===================================================================
def render_clipboard_and_download_bar(
    markdown_content: str = "",
    default_filename: str = "Obsidian_Note.md",
    key_prefix: str = "obs",
    note_type: str = "general",
    source_books: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    **kwargs
):
    """
    渲染標準第二大腦操作列：
      1. 💾 存入第二大腦筆記庫 (Vault)
      2. 📋 複製 Markdown 內容至剪貼簿
      3. 📥 下載 .md 檔案
    """
    content = markdown_content or kwargs.get("content", "")
    sources = source_books or []

    # 處理 docs 來源參數
    docs = kwargs.get("docs")
    if docs and isinstance(docs, (list, tuple)):
        for d in docs:
            if hasattr(d, "metadata") and isinstance(d.metadata, dict):
                s = d.metadata.get("filename") or d.metadata.get("source")
                if s and os.path.basename(str(s)) not in sources:
                    sources.append(os.path.basename(str(s)))
            elif isinstance(d, dict):
                s = d.get("filename") or d.get("source")
                if s and os.path.basename(str(s)) not in sources:
                    sources.append(os.path.basename(str(s)))

    # 動態生成絕對唯一的 Element Key
    unique_key = _generate_unique_key(key_prefix, content, default_filename, **kwargs)

    col_save, col_copy, col_dl = st.columns([1.3, 1.1, 1.1])

    # 1. 存入第二大腦
    with col_save:
        btn_save_key = f"btn_vault_save_{unique_key}"
        if st.button("💾 存入第二大腦", key=btn_save_key, use_container_width=True, help="永久保存至個人第二大腦筆記庫 (vault_notes/)"):
            title = default_filename.replace(".md", "")
            success, msg, _ = VaultManager.save_note(
                title=title,
                content=content,
                note_type=note_type,
                source_books=sources,
                tags=tags
            )
            if success:
                st.toast(f"🎉 {msg}", icon="🧠")
            else:
                st.error(msg)

    # 2. 剪貼簿一鍵複製
    with col_copy:
        _render_copy_button(content, key_prefix=f"bar_{unique_key}")

    # 3. 下載 .md 檔案
    with col_dl:
        st.download_button(
            label="📥 下載 .md",
            data=content.encode("utf-8"),
            file_name=default_filename,
            mime="text/markdown",
            key=f"btn_dl_{unique_key}",
            use_container_width=True
        )


# ===================================================================
# 3. 舊版介面相容入口
# ===================================================================
def render_obsidian_button(
    markdown_content: Optional[str] = None,
    default_filename: Optional[str] = None,
    key_prefix: str = "obs",
    note_type: str = "general",
    source_books: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    engine: Any = None,
    content: Optional[str] = None,
    docs: Any = None,
    query: Optional[str] = None,
    topic: Optional[str] = None,
    **kwargs
):
    """相容舊版介面呼叫，自動推導標題、來源書籍並防止 Key 衝突。"""
    final_content = markdown_content or content or kwargs.get("text", "")
    final_query = query or topic or kwargs.get("title", "")

    # 自動推導檔案名稱
    if not default_filename:
        if final_query:
            clean_q = re.sub(r'[\\/*?:"<>|#\[\]]', '', str(final_query)).strip()[:25]
            default_filename = f"QA_{clean_q}.md" if clean_q else "Obsidian_Note.md"
        else:
            default_filename = "Obsidian_Note.md"

    # 自動推導筆記型態
    final_type = note_type
    if note_type == "general":
        if "insight" in str(key_prefix).lower():
            final_type = "daily_insight"
        elif final_query:
            final_type = "qa_insight"

    render_clipboard_and_download_bar(
        markdown_content=final_content,
        default_filename=default_filename,
        key_prefix=key_prefix,
        note_type=final_type,
        source_books=source_books,
        tags=tags,
        docs=docs,
        **kwargs
    )