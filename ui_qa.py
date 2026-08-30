# -*- coding: utf-8 -*-
"""
智能問答頁面 (ui_qa.py)
========================
負責：
  1. 對話訊息歷史展示與流暢問答體驗
  2. 回答下方內嵌「微型操作列 (Action Bar)」：一鍵複製、本題深度綜整、Obsidian 筆記生成
  3. 卡片式參考來源展示（檔案類型圖標、章節標註、Reranker 相關度得分徽章）
  4. CoT 思考推演過程與檢索技術日誌折疊區
"""

import streamlit as st
from obsidian_helper import render_obsidian_button, _render_copy_button


def _render_source_card(idx: int, doc):
    """將單一文獻片段渲染為結構化資訊卡片（含類型、來源書籍、章節與相關度徽章）。"""
    metadata = getattr(doc, "metadata", {}) or {}
    filename = metadata.get("filename") or metadata.get("source", "未知來源")
    chapter = metadata.get("chapter", "")
    file_type = metadata.get("file_type", "")
    if not file_type:
        ext = filename.split(".")[-1].lower() if "." in filename else ""
        file_type = ext if ext in ("pdf", "epub", "txt") else "文件"

    rerank_score = metadata.get("rerank_score", None)

    # 檔案格式徽章
    type_badges = {
        "pdf": "📄 PDF",
        "epub": "📖 EPUB",
        "txt": "📝 TXT"
    }
    type_label = type_badges.get(file_type.lower(), f"📎 {file_type.upper()}")

    # 相關度分數徽章 (Rerank Score)
    if rerank_score is not None:
        score_val = float(rerank_score)
        if score_val >= 0.7:
            score_badge = f"🟢 相關度: {score_val:.2f}"
        elif score_val >= 0.4:
            score_badge = f"🟡 相關度: {score_val:.2f}"
        else:
            score_badge = f"⚪ 相關度: {score_val:.2f}"
    else:
        score_badge = "🎯 檢索命中"

    chapter_label = f"・*{chapter}*" if chapter else ""
    header_markdown = f"**來源 #{idx}** &nbsp;|&nbsp; `{type_label}` &nbsp;**《{filename}》**{chapter_label} &nbsp;|&nbsp; `{score_badge}`"

    st.markdown(header_markdown)
    content = getattr(doc, "page_content", str(doc)).strip()
    st.markdown(f"> {content}")
    st.divider()


def render_qa_page(engine):
    """渲染智能問答主頁面。"""
    st.subheader("💬 智能書籍問答")
    st.caption("基於兩階段混合檢索 (向量 + BM25 + Cross-Encoder Reranker) 與大語言模型，深度解析書庫知識。")

    # 初始化 Session State
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "synthesis_results" not in st.session_state:
        st.session_state.synthesis_results = {}

    # 頂部控制項
    col_opt1, col_opt2 = st.columns([3, 1])
    with col_opt1:
        use_thinking = st.checkbox(
            "🧠 啟用深度思考模式 (CoT)",
            value=False,
            help="開啟後 AI 會先輸出邏輯推演過程 (<thinking>) 再給出答案，提升複雜問題的推論深度。"
        )
    with col_opt2:
        if st.button("🗑️ 清空對話歷史", use_container_width=True):
            st.session_state.messages = []
            st.session_state.synthesis_results = {}
            st.rerun()

    # 渲染對話歷史流
    for msg_idx, msg in enumerate(st.session_state.messages):
        role = msg["role"]
        with st.chat_message(role):
            st.markdown(msg["content"])

            if role == "assistant":
                is_stat = msg.get("is_stat_query", False)
                thinking = msg.get("thinking_process", "")
                log = msg.get("log", "")
                sources = msg.get("sources", [])
                turn_question = msg.get("associated_question", "")

                # 1. 深度思考推演
                if not is_stat and thinking:
                    with st.expander("🧠 檢視 AI 深度思考推演過程", expanded=False):
                        st.markdown(thinking)

                # 2. 結構化參考來源卡片
                if not is_stat and sources:
                    with st.expander(f"📚 檢視參考文獻來源（共 {len(sources)} 筆精華片段）", expanded=False):
                        for s_idx, src_doc in enumerate(sources, start=1):
                            _render_source_card(s_idx, src_doc)

                # 3. 檢索技術日誌
                if not is_stat and log:
                    with st.expander("🛠️ 檢視檢索與重排序技術日誌", expanded=False):
                        st.code(log, language="markdown")

                # 4. 回答下方微型操作列 (Action Bar)
                if not is_stat and msg["content"]:
                    st.markdown("---")
                    col_copy, col_syn, col_obs = st.columns([1.2, 1.5, 1.5])

                    with col_copy:
                        _render_copy_button(msg["content"], button_id=f"copy_ans_{msg_idx}")

                    with col_syn:
                        if st.button("🔬 本題深度綜整", key=f"btn_syn_{msg_idx}", use_container_width=True):
                            with st.spinner("AI 正在閱讀所有關聯文獻，產出結構化綜整報告..."):
                                syn_res = engine.generate_deep_synthesis(
                                    question=turn_question or "專題深度分析",
                                    retrieved_docs=sources
                                )
                                if syn_res.get("status") == "success":
                                    st.session_state.synthesis_results[msg_idx] = syn_res.get("content", "")
                                    st.rerun()
                                else:
                                    st.error(f"綜整失敗：{syn_res.get('content', '未知錯誤')}")

                    with col_obs:
                        if "obsidian_engine" not in st.session_state:
                            from obsidian_engine import ObsidianEngine
                            st.session_state.obsidian_engine = ObsidianEngine(llm=engine.llm)

                        render_obsidian_button(
                            engine=st.session_state.obsidian_engine,
                            content=msg["content"],
                            docs=sources,
                            topic=turn_question or "書籍問答筆記",
                            button_key=f"obs_qa_{msg_idx}",
                            label="📝 轉 Obsidian 筆記",
                            note_type="deep_dive"
                        )

                    # 若該則回答已生成深度綜整，於正下方以高亮區塊展示
                    if msg_idx in st.session_state.synthesis_results:
                        syn_content = st.session_state.synthesis_results[msg_idx]
                        st.markdown("#### 📑 專題深度綜整報告")
                        with st.expander("展開檢視完整綜整分析", expanded=True):
                            st.markdown(syn_content)

                            col_syn_cp, col_syn_ob = st.columns([1, 1])
                            with col_syn_cp:
                                _render_copy_button(syn_content, button_id=f"copy_syn_{msg_idx}")
                            with col_syn_ob:
                                render_obsidian_button(
                                    engine=st.session_state.obsidian_engine,
                                    content=syn_content,
                                    docs=sources,
                                    topic=f"{turn_question} - 深度綜整",
                                    button_key=f"obs_syn_{msg_idx}",
                                    label="📝 將綜整報告轉 Obsidian 筆記",
                                    note_type="synthesis"
                                )

    # 使用者對話輸入框
    if prompt := st.chat_input("請輸入關於書籍內容的問題..."):
        # 記錄使用者訊息
        st.session_state.messages.append({
            "role": "user",
            "content": prompt
        })

        with st.chat_message("user"):
            st.markdown(prompt)

        # 生成 Assistant 回答
        with st.chat_message("assistant"):
            spinner_msg = "AI 正在兩階段檢索書庫並深入思考..." if use_thinking else "AI 正在檢索書庫並整合答案..."
            with st.spinner(spinner_msg):
                result = engine.query(prompt, use_thinking=use_thinking)

            answer = result.get("answer", "")
            sources = result.get("sources", [])
            is_stat = result.get("is_stat_query", False)
            log = result.get("log", "")
            thinking = result.get("thinking_process", "")

            st.markdown(answer)

            if not is_stat and thinking:
                with st.expander("🧠 檢視 AI 深度思考推演過程", expanded=False):
                    st.markdown(thinking)

            if not is_stat and sources:
                with st.expander(f"📚 檢視參考文獻來源（共 {len(sources)} 筆精華片段）", expanded=False):
                    for s_idx, src_doc in enumerate(sources, start=1):
                        _render_source_card(s_idx, src_doc)

            if not is_stat and log:
                with st.expander("🛠️ 檢視檢索與重排序技術日誌", expanded=False):
                    st.code(log, language="markdown")

        # 儲存至對話歷史
        st.session_state.messages.append({
            "role": "assistant",
            "content": answer,
            "sources": sources,
            "is_stat_query": is_stat,
            "log": log,
            "thinking_process": thinking,
            "associated_question": prompt,
        })
        st.rerun()