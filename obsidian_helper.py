# -*- coding: utf-8 -*-
"""
Obsidian 筆記共用元件 (obsidian_helper.py)
==========================================
提供跨頁面（智能問答、知識圖譜、每日書摘）通用的「一鍵生成 Obsidian 筆記」UI 渲染元件。
支援：
  1. 4 種筆記模式生成
  2. 零摩擦「一鍵複製 Markdown」與「下載 .md 檔案」雙操作通道
"""

import re
import html
from datetime import datetime
from typing import List, Any, Optional
import streamlit as st
import streamlit.components.v1 as components
from obsidian_engine import ObsidianEngine


def _render_copy_button(text_content: str, button_id: str):
    """渲染純前端免跳轉的一鍵複製剪貼簿按鈕。"""
    escaped_text = html.escape(text_content).replace("\n", "\\n").replace("\r", "").replace("'", "\\'")
    copy_html = f"""
    <button id="btn_{button_id}" onclick="copyText_{button_id}()" style="
        width: 100%;
        background-color: #262730;
        color: #ffffff;
        border: 1px solid rgba(250, 250, 250, 0.2);
        padding: 0.55rem 1rem;
        font-size: 0.9rem;
        border-radius: 0.5rem;
        cursor: pointer;
        font-weight: 500;
        transition: all 0.2s ease;
    ">📋 複製 Markdown 筆記</button>

    <script>
    function copyText_{button_id}() {{
        const text = '{escaped_text}';
        navigator.clipboard.writeText(text).then(() => {{
            const btn = document.getElementById('btn_{button_id}');
            const originalText = btn.innerText;
            btn.innerText = '✅ 已複製到剪貼簿！';
            btn.style.backgroundColor = '#0e703c';
            setTimeout(() => {{
                btn.innerText = originalText;
                btn.style.backgroundColor = '#262730';
            }}, 2500);
        }}).catch(err => {{
            alert('複製失敗，請手動複製代碼框內容');
        }});
    }}
    </script>
    """
    components.html(copy_html, height=45)


def render_obsidian_button(
    engine: ObsidianEngine,
    content: str,
    docs: List[Any],
    topic: str,
    button_key: str,
    label: str = "🗒️ 轉成 Obsidian 筆記",
    note_type: str = "synthesis",
    custom_tags: Optional[List[str]] = None
):
    """
    渲染「轉成 Obsidian 筆記」按鈕及其即時 Markdown 預覽、一鍵複製與下載區塊。
    """
    note_key = f"obsidian_note_{button_key}"
    preview_key = f"obsidian_preview_{button_key}"

    if st.button(label, key=f"btn_{button_key}", use_container_width=True):
        if not content or len(content.strip()) < 5:
            st.warning("目前無足夠的內文可供轉換為筆記。")
            return

        with st.spinner("AI 正在研讀文獻並編撰 Obsidian 筆記..."):
            result = engine.generate_obsidian_note(
                topic=topic,
                docs=docs,
                note_type=note_type,
                custom_tags=custom_tags
            )

        if result["status"] == "success":
            st.session_state[note_key] = result["content"]
            st.session_state[preview_key] = True
        else:
            st.error(f"生成失敗：{result['content']}")

    if st.session_state.get(preview_key, False):
        note_content = st.session_state.get(note_key, "")

        if note_content:
            st.markdown("---")
            st.subheader("📝 Obsidian 筆記預覽")

            with st.expander("展開檢視完整 Markdown 內容", expanded=True):
                st.markdown(note_content)

            clean_topic = re.sub(r'[\\/*?:"<>| ]', '_', topic)[:30].strip('_')
            if not clean_topic:
                clean_topic = "知識筆記"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"Obsidian_{clean_topic}_{timestamp}.md"

            col_copy, col_dl, col_close = st.columns([2, 2, 1])

            with col_copy:
                _render_copy_button(note_content, button_id=button_key)

            with col_dl:
                st.download_button(
                    label="⬇️ 下載 .md 檔案",
                    data=note_content,
                    file_name=filename,
                    mime="text/markdown",
                    key=f"download_{button_key}",
                    type="primary",
                    use_container_width=True
                )

            with col_close:
                if st.button("✖️ 關閉", key=f"close_{button_key}", use_container_width=True):
                    st.session_state[preview_key] = False
                    st.session_state[note_key] = ""
                    st.rerun()