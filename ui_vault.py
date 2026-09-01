# -*- coding: utf-8 -*-
"""
第二大腦筆記庫管理介面 (ui_vault.py)
====================================
負責：
  1. 🧠 第二大腦知識庫儀表板 (筆記總數、字數、標籤分佈、關聯書目)
  2. 📑 Master-Detail 雙欄式筆記瀏覽器 (左清單、右預覽)
  3. 🔍 依筆記型態、關聯書籍、標籤或關鍵字即時檢索過濾
  4. 📝 渲染預覽 / 原始 Markdown 檢視切換、一鍵複製、重新下載與刪除
  5. 📦 一鍵打包全部筆記為 ZIP 匯出
"""

import os
import streamlit as st
from vault_manager import VaultManager
from obsidian_helper import render_clipboard_and_download_bar


TYPE_LABELS = {
    "deep_dive": "📘 單書精讀申論",
    "synthesis": "🌐 多書交叉綜整",
    "atomic_card": "💡 原子概念卡片",
    "critique": "⚖️ 批判思維檢視",
    "qa_insight": "💬 問答對話洞察",
    "daily_insight": "☀️ 今日靈感書摘",
    "general": "📝 綜合筆記"
}


def render_vault_page():
    """渲染第二大腦筆記庫主頁面。"""
    st.subheader("🧠 第二大腦筆記庫 (Second Brain Vault)")
    st.caption("所有由私人圖書館提煉的知識晶體、專題申論與對話洞察皆沉澱於此，支援 Obsidian 雙向連結與標籤管理。")

    notes = VaultManager.list_notes()

    # ------------------------------------------------------------- 統計儀表板
    total_notes = len(notes)
    total_words = sum(n.get("word_count", 0) for n in notes)
    
    # 提取所有不重複標籤與書籍
    all_tags = set()
    all_sources = set()
    for n in notes:
        for t in n.get("tags", []):
            all_tags.add(t)
        for s in n.get("sources", []):
            all_sources.add(s)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📑 筆記庫存量", f"{total_notes} 篇")
    c2.metric("✍️ 累計知識字數", f"{total_words:,} 字")
    c3.metric("🏷️ 概念標籤數", f"{len(all_tags)} 個")
    c4.metric("📚 連結書目", f"{len(all_sources)} 本")

    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

    if total_notes == 0:
        st.info("💡 您的第二大腦庫目前尚無筆記！在「💬 智能問答」、「🕸️ 知識圖譜（今日書摘）」或「📝 Obsidian 筆記工作室」中生成內容後，點擊「💾 存入第二大腦」，結晶將自動保存在此。")
        return

    # ------------------------------------------------------------- 篩選與工具列
    with st.container(border=True):
        f_col1, f_col2, f_col3, f_col4 = st.columns([1.5, 1.5, 2, 1.2])
        
        with f_col1:
            type_options = ["全部類型"] + list(TYPE_LABELS.values())
            sel_type = st.selectbox("筆記類型篩選", options=type_options, index=0)
            
        with f_col2:
            tag_options = ["全部標籤"] + sorted(list(all_tags))
            sel_tag = st.selectbox("標籤篩選", options=tag_options, index=0)
            
        with f_col3:
            kw = st.text_input("🔍 搜尋筆記標題或內文", placeholder="輸入關鍵字檢索...").strip().lower()

        with f_col4:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            zip_data = VaultManager.export_all_as_zip()
            if zip_data:
                st.download_button(
                    label="📦 打包匯出",
                    data=zip_data,
                    file_name="Second_Brain_Vault.zip",
                    mime="application/zip",
                    use_container_width=True,
                    help="將所有 Markdown 筆記打包為 ZIP 下載"
                )

    # 執行過濾
    filtered_notes = []
    for n in notes:
        ntype_label = TYPE_LABELS.get(n.get("note_type", "general"), "📝 綜合筆記")
        
        if sel_type != "全部類型" and ntype_label != sel_type:
            continue
        if sel_tag != "全部標籤" and sel_tag not in n.get("tags", []):
            continue
        if kw:
            in_title = kw in n.get("title", "").lower()
            in_content = kw in n.get("content", "").lower()
            if not (in_title or in_content):
                continue
        filtered_notes.append(n)

    st.markdown(f"**符合條件的筆記**（共 **{len(filtered_notes)}** 篇）：")

    # ------------------------------------------------------------- 主從式雙欄佈局 (Master-Detail)
    col_list, col_viewer = st.columns([1.3, 2.2])

    # 記錄目前選中的筆記
    if "selected_vault_note" not in st.session_state or not any(n["filename"] == st.session_state["selected_vault_note"] for n in filtered_notes):
        if filtered_notes:
            st.session_state["selected_vault_note"] = filtered_notes[0]["filename"]
        else:
            st.session_state["selected_vault_note"] = None

    # 左欄：筆記列表
    with col_list:
        st.markdown("##### 📑 筆記索引清單")
        
        for n in filtered_notes:
            fname = n["filename"]
            title = n["title"]
            ntype = n.get("note_type", "general")
            ntype_label = TYPE_LABELS.get(ntype, "📝 綜合筆記")
            mtime = n["modified_at"]
            wcount = n["word_count"]
            is_active = (st.session_state.get("selected_vault_note") == fname)

            border_style = "border-left: 4px solid #7C3AED;" if is_active else "border-left: 1px solid rgba(255,255,255,0.1);"
            bg_style = "background-color: rgba(124, 58, 237, 0.1);" if is_active else ""

            with st.container():
                st.markdown(
                    f"""
                    <div style='padding: 8px 12px; margin-bottom: 6px; border-radius: 6px; {border_style} {bg_style}'>
                        <div style='font-size: 15px; font-weight: bold;'>{title}</div>
                        <div style='font-size: 12px; color: #888; margin-top: 2px;'>
                            {ntype_label} &nbsp;|&nbsp; {wcount} 字 &nbsp;|&nbsp; {mtime}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                btn_pick_key = f"pick_{fname}"
                if st.button("📖 閱讀此筆記", key=btn_pick_key, use_container_width=True):
                    st.session_state["selected_vault_note"] = fname
                    st.rerun()

    # 右欄：筆記詳情與預覽器
    with col_viewer:
        active_fname = st.session_state.get("selected_vault_note")
        if not active_fname:
            st.info("請從左側清單選取要檢視的筆記。")
            return

        active_note = next((n for n in notes if n["filename"] == active_fname), None)
        if not active_note:
            st.warning("找不到選定的筆記內容。")
            return

        with st.container(border=True):
            # 筆記頂部標題與操作
            top_c1, top_c2 = st.columns([3, 1])
            with top_c1:
                st.markdown(f"### 📝 {active_note['title']}")
                ntype_label = TYPE_LABELS.get(active_note['note_type'], '📝 綜合筆記')
                st.caption(f"類型：`{ntype_label}` &nbsp;|&nbsp; 字數：`{active_note['word_count']} 字` &nbsp;|&nbsp; 更新：`{active_note['modified_at']}`")
            with top_c2:
                # 刪除確認
                del_key = f"vault_del_{active_fname}"
                if st.button("🗑️ 刪除筆記", key=f"btn_{del_key}", use_container_width=True):
                    st.session_state[del_key] = True

            if st.session_state.get(del_key, False):
                st.warning(f"⚠️ 確定要從第二大腦刪除《{active_fname}》嗎？")
                d_c1, d_c2 = st.columns(2)
                with d_c1:
                    if st.button("❌ 取消", key=f"cancel_{del_key}", use_container_width=True):
                        st.session_state[del_key] = False
                        st.rerun()
                with d_c2:
                    if st.button("✅ 確定刪除", key=f"confirm_{del_key}", type="primary", use_container_width=True):
                        VaultManager.delete_note(active_fname)
                        st.session_state[del_key] = False
                        st.session_state["selected_vault_note"] = None
                        st.toast("已成功刪除筆記！")
                        st.rerun()

            # 標籤與關聯書籍徽章
            tags = active_note.get("tags", [])
            sources = active_note.get("sources", [])
            if tags or sources:
                badges_md = " ".join([f"`{t}`" for t in tags]) + " " + " ".join([f"📖 `{s}`" for s in sources])
                st.markdown(badges_md)

            st.divider()

            # 操作列（複製 / 下載）
            render_clipboard_and_download_bar(
                markdown_content=active_note["content"],
                default_filename=active_fname,
                key_prefix=f"vault_view_{active_fname}",
                note_type=active_note.get("note_type", "general"),
                source_books=sources,
                tags=tags
            )

            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

            # 檢視切換：渲染模式 vs 原始 Markdown
            view_tab1, view_tab2 = st.tabs(["👁️ 渲染預覽", "💻 原始 Markdown 代碼"])
            with view_tab1:
                st.markdown(active_note["content"])
            with view_tab2:
                st.code(active_note["content"], language="markdown")