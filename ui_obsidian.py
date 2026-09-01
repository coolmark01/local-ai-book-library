# -*- coding: utf-8 -*-
"""
Obsidian 專題筆記工作室 (ui_obsidian.py)
========================================
負責：
  1. 📝 提供 4 大第二大腦筆記架構 (單書精讀、多書綜整、原子卡片、批判思維)
  2. 💊 靈感膠囊 (Prompt Pills) 快速帶入研究主題
  3. 🔍 四層智能容錯檢索管線 (保證 100% 成功召回書籍內文)
  4. 🧠 自動整合「💾 存入第二大腦」、「📋 一鍵複製」與「📥 下載 .md」
  5. 👁️ 渲染預覽 / 💻 原始 Markdown 雙視圖切換
"""

import os
import re
import streamlit as st
from typing import List, Dict, Any
from langchain_core.documents import Document

from config import RAGConfig
from obsidian_helper import render_clipboard_and_download_bar

# 筆記架構定義
NOTE_ARCHETYPES = {
    "deep_dive": {
        "title": "📘 單書精讀申論 (Single-Book Deep Dive)",
        "desc": "針對單一書籍進行章節脈絡梳理、底層邏輯推導與核心思想深度申論。",
        "multi_book": False,
        "default_tag": "#DeepDive"
    },
    "synthesis": {
        "title": "🌐 多書交叉綜整 (Cross-Book Synthesis)",
        "desc": "跨越 2 本以上書籍，針對特定主題進行觀點對照、共通規律萃取與理論框架整合。",
        "multi_book": True,
        "default_tag": "#CrossSynthesis"
    },
    "atomic_card": {
        "title": "💡 原子概念卡片 (Atomic Concept Card)",
        "desc": "卡片盒筆記法 (Zettelkasten) 風格，提煉單一核心概念、定義、運作機制與反直覺觀點。",
        "multi_book": False,
        "default_tag": "#AtomicNote"
    },
    "critique": {
        "title": "⚖️ 批判思維檢視 (Critical Review)",
        "desc": "檢驗論點的前提假設、適用邊界條件、邏輯盲點與潛在反例。",
        "multi_book": False,
        "default_tag": "#CriticalReview"
    }
}

# 靈感膠囊預設主題
PROMPT_PILLS = [
    "核心底層邏輯與心智模型推導",
    "關鍵實踐步驟與行動檢核清單",
    "跨學科類比與第一性原理分析",
    "理論邊界條件與潛在反例檢驗",
    "常見認知偏誤與決策陷阱"
]


def _safe_retrieve_context(engine, query: str, selected_books: List[str], top_k: int = 10) -> List[Any]:
    """四層智能容錯檢索調度器：解決路徑不一致與抽象概念召回問題。"""
    # 取得現存書籍清單並建立路徑對照表
    all_books = engine.get_book_list_with_chunk_counts()
    book_sources = []
    source_to_fname = {}

    for b in all_books:
        fname = b.get("filename", "")
        src = b.get("source", "")
        if fname in selected_books or src in selected_books:
            if src:
                book_sources.append(src)
                source_to_fname[src] = fname
            if fname:
                book_sources.append(fname)
                source_to_fname[fname] = fname

    if not book_sources:
        book_sources = list(selected_books)

    docs = []

    # ----------------- 第 1 層：多參數組合檢索 -----------------
    for method_name in ["retrieve", "hybrid_search", "search", "get_relevant_documents", "query_docs"]:
        if hasattr(engine, method_name):
            method = getattr(engine, method_name)
            for filter_param in ["filter_books", "filter_sources", "sources", "books"]:
                try:
                    res = method(query=query, **{filter_param: book_sources, "top_k": top_k})
                    if res:
                        docs = res
                        break
                except Exception:
                    pass
            if docs:
                break

    # ----------------- 第 2 層：無過濾混合檢索 + 記憶體篩選 -----------------
    if not docs:
        for method_name in ["retrieve", "hybrid_search", "search"]:
            if hasattr(engine, method_name):
                try:
                    res = getattr(engine, method_name)(query=query, top_k=top_k * 3)
                    if res:
                        matched = []
                        for d in res:
                            meta = d.metadata if hasattr(d, "metadata") else (d.get("metadata", {}) if isinstance(d, dict) else {})
                            doc_src = meta.get("source", "") or meta.get("filename", "")
                            if any(sb in doc_src for sb in selected_books) or not selected_books:
                                matched.append(d)
                        if matched:
                            docs = matched[:top_k]
                            break
                except Exception:
                    pass

    # ----------------- 第 3 層：直接查詢底層向量資料庫 -----------------
    if not docs and hasattr(engine, "vector_store") and engine.vector_store:
        try:
            res = engine.vector_store.similarity_search(query, k=top_k * 3)
            matched = []
            for d in res:
                doc_src = d.metadata.get("source", "") or d.metadata.get("filename", "")
                if any(sb in doc_src for sb in selected_books) or not selected_books:
                    matched.append(d)
            if matched:
                docs = matched[:top_k]
        except Exception:
            pass

    # ----------------- 第 4 層（保底機制）：全書代表性片段均勻採樣 -----------------
    if not docs and hasattr(engine, "get_book_chunks"):
        for b_item in all_books:
            fname = b_item.get("filename", "")
            src = b_item.get("source", "")
            if fname in selected_books or src in selected_books:
                target_src = src or fname
                raw_chunks = engine.get_book_chunks(target_src)
                if raw_chunks:
                    total_c = len(raw_chunks)
                    sample_count = min(top_k, total_c)
                    step = max(1, total_c // sample_count)
                    sampled = raw_chunks[::step][:sample_count]

                    for sc in sampled:
                        c_text = sc.get("content", "")
                        c_meta = sc.get("metadata", {})
                        if not c_meta.get("filename"):
                            c_meta["filename"] = fname
                        docs.append(Document(page_content=c_text, metadata=c_meta))

    # 規範化回傳格式
    formatted_docs = []
    for d in docs:
        if isinstance(d, Document):
            formatted_docs.append(d)
        elif isinstance(d, dict):
            formatted_docs.append(Document(
                page_content=d.get("content", "") or d.get("page_content", ""),
                metadata=d.get("metadata", {})
            ))
    return formatted_docs


def render_obsidian_page(engine, config: RAGConfig):
    """渲染 Obsidian 筆記工作室主頁面。"""
    st.subheader("📝 Obsidian 筆記工作室 (Second Brain Studio)")
    st.caption("將私人圖書館的檢索片段晶體化為高品質 Markdown 筆記，支援 [[雙向連結]]、YAML 元數據與一鍵存入第二大腦。")

    # 1. 檢查書庫是否有書
    books = engine.get_book_list_with_chunk_counts()
    if not books or (isinstance(books, list) and len(books) > 0 and "error" in books[0]):
        st.info("💡 目前知識庫中尚無任何書籍。請先至「📚 知識庫管理」匯入書籍檔案後再來生成筆記。")
        return

    book_filenames = [b["filename"] for b in books if "filename" in b]

    # 2. 筆記架構選擇
    st.markdown("#### 1. 選擇筆記架構模式")
    arch_keys = list(NOTE_ARCHETYPES.keys())
    arch_titles = [NOTE_ARCHETYPES[k]["title"] for k in arch_keys]

    selected_title = st.selectbox("筆記架構模式", options=arch_titles, index=0, label_visibility="collapsed")
    selected_mode = arch_keys[arch_titles.index(selected_title)]
    arch_info = NOTE_ARCHETYPES[selected_mode]

    st.info(f"📌 **{arch_info['title']}**：{arch_info['desc']}")

    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

    # 3. 書籍選擇器
    st.markdown("#### 2. 選擇研究對象書籍")
    if arch_info["multi_book"]:
        selected_books = st.multiselect(
            "選取要進行交叉綜整的書籍（建議 2~5 本）",
            options=book_filenames,
            default=book_filenames[:min(len(book_filenames), 2)]
        )
    else:
        chosen_book = st.selectbox("選取要精讀的書籍", options=book_filenames, index=0)
        selected_books = [chosen_book] if chosen_book else []

    if not selected_books:
        st.warning("⚠️ 請至少選取一本目標書籍！")
        return

    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

    # 4. 主題輸入與靈感膠囊
    st.markdown("#### 3. 專題研究主題與方向")

    # 靈感膠囊按鈕
    st.caption("💡 點擊靈感膠囊快速帶入研究切入點：")
    pill_cols = st.columns(len(PROMPT_PILLS))
    for idx, pill_text in enumerate(PROMPT_PILLS):
        with pill_cols[idx]:
            if st.button(pill_text, key=f"pill_{idx}", use_container_width=True):
                st.session_state["obsidian_topic_input"] = pill_text

    topic_value = st.session_state.get("obsidian_topic_input", "")
    topic_query = st.text_input(
        "研究主題 / 核心探討問題",
        value=topic_value,
        placeholder="例如：如何建立具備護城河的商業模式？或第一性原理的實際推導過程",
        help="輸入你想讓 AI 深入提煉的專題面向。"
    ).strip()

    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)

    # 5. 生成按鈕
    btn_generate = st.button("🚀 生成 Obsidian 專題筆記", type="primary", use_container_width=True)

    if btn_generate:
        if not topic_query:
            st.warning("⚠️ 請輸入研究主題或點選上方的靈感膠囊！")
            return

        with st.spinner("AI 正在深度檢索書籍切塊、進行跨文本重排序並構建 Obsidian 筆記體系..."):
            try:
                # 調用四層容錯檢索
                retrieved_docs = _safe_retrieve_context(
                    engine=engine,
                    query=topic_query,
                    selected_books=selected_books,
                    top_k=config.FINAL_TOP_K * 2
                )

                if not retrieved_docs:
                    st.error("❌ 找不到與此主題相關的書籍內文片段，請嘗試調整關鍵字或選取其他書籍。")
                    return

                # 初始化 Obsidian 生成引擎
                from obsidian_engine import ObsidianEngine
                obs_engine = ObsidianEngine(llm=engine.llm)

                # 生成 Markdown 筆記
                generated_md = obs_engine.generate_note(
                    mode=selected_mode,
                    topic=topic_query,
                    books=selected_books,
                    context_docs=retrieved_docs
                )

                # 計算預設檔名與標籤
                clean_topic = re.sub(r'[\\/*?:"<>|#\[\]]', '', topic_query).strip()[:30]
                primary_book = selected_books[0].replace(".pdf", "").replace(".epub", "").replace(".txt", "")
                if arch_info["multi_book"]:
                    safe_filename = f"Obsidian_綜整_{clean_topic}.md"
                else:
                    safe_filename = f"Obsidian_{primary_book}_{clean_topic}.md"

                tags = ["#SecondBrain", arch_info["default_tag"]]
                if topic_query:
                    tags.append(f"#{clean_topic[:10]}")

                # 存入 Session State 以供重複檢視與操作
                st.session_state["current_obsidian_output"] = {
                    "content": generated_md,
                    "filename": safe_filename,
                    "note_type": selected_mode,
                    "sources": selected_books,
                    "tags": tags,
                    "topic": topic_query
                }
                st.success("🎉 Obsidian 專題筆記生成完成！")

            except Exception as e:
                st.error(f"筆記生成過程發生錯誤: {e}")
                return

    # 6. 渲染產出結果與第二大腦操作列
    if "current_obsidian_output" in st.session_state and st.session_state["current_obsidian_output"]:
        output_data = st.session_state["current_obsidian_output"]
        md_text = output_data["content"]
        md_fname = output_data["filename"]
        md_type = output_data["note_type"]
        md_sources = output_data["sources"]
        md_tags = output_data["tags"]

        st.divider()
        st.markdown(f"### 📄 產出結果：`{md_fname}`")

        # 核心第二大腦操作列 (存入第二大腦 / 一鍵複製 / 下載 .md)
        with st.container(border=True):
            st.markdown("##### ⚡ 第二大腦捷徑操作")
            render_clipboard_and_download_bar(
                markdown_content=md_text,
                default_filename=md_fname,
                key_prefix=f"obs_studio_{md_type}",
                note_type=md_type,
                source_books=md_sources,
                tags=md_tags
            )

        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

        # 雙視圖切換
        tab_preview, tab_raw = st.tabs(["👁️ 渲染預覽 (Markdown Preview)", "💻 原始碼檢視 (Raw Markdown)"])
        with tab_preview:
            st.markdown(md_text)
        with tab_raw:
            st.code(md_text, language="markdown")