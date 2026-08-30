"""
知識圖譜頁面 (ui_knowledge.py)
================================
負責：詞雲展示、每日書摘 UI、書摘轉 Obsidian 筆記。
修改圖譜 UI 或新增功能時只需編輯此檔案。
"""

import streamlit as st

from config import RAGConfig
from obsidian_helper import render_obsidian_button  # [NEW]


def render_knowledge_page(engine, config: RAGConfig):
    """渲染知識圖譜頁面。"""
    st.subheader("知識可視化")

    tab1, tab2 = st.tabs(["關鍵詞詞雲", "今日書摘"])

    # --- Tab 1: 詞雲 ---
    with tab1:
        st.write("從您的書庫中提取高頻關鍵詞：")
        if st.button("生成詞雲"):
            with st.spinner("正在分析全庫數據..."):
                viz = engine.viz_engine
                if viz and engine.vectorstore:
                    word_freq = viz.get_word_cloud_data(limit=config.WORD_CLOUD_TOP_N)
                    if word_freq:
                        plt_obj = viz.generate_word_cloud_image(word_freq)
                        if plt_obj:
                            st.pyplot(plt_obj)
                            st.caption(f"共提取 {len(word_freq)} 個關鍵詞")
                        else:
                            st.error("生成詞雲失敗，請檢查系統字體路徑。")
                    else:
                        st.warning("書庫為空或數據不足，無法生成詞雲。")
                else:
                    st.error("可視化引擎未就緒，請確認書庫已正確初始化。")

    # --- Tab 2: 每日書摘 ---
    with tab2:
        st.write("讓 AI 從書庫中為您提煉一段今日讀書洞察：")

        # 顯示已存儲的洞察
        if st.session_state.get("daily_insight"):
            st.info(st.session_state.daily_insight)

        if st.button("獲取今日書摘"):
            with st.spinner("正在閱讀書庫並思考..."):
                if engine.llm:
                    insight = engine.viz_engine.get_daily_insight(engine.llm, config)
                    st.session_state.daily_insight = insight
                    st.info(insight)
                else:
                    msg = "LLM 尚未就緒，無法生成書摘。"
                    st.session_state.daily_insight = msg
                    st.info(msg)

        # ============================================================
        # [NEW] Obsidian 筆記生成區 - 書摘轉筆記
        # ============================================================
        daily_insight = st.session_state.get("daily_insight")

        if daily_insight and len(daily_insight.strip()) > 5:
            st.divider()
            st.caption("匯出為 Obsidian 筆記")

            # 初始化 ObsidianEngine（延遲初始化）
            if "obsidian_engine" not in st.session_state:
                from obsidian_engine import ObsidianEngine
                st.session_state.obsidian_engine = ObsidianEngine(llm=engine.llm)

            # 嘗試取得書摘相關的來源文檔
            # 書摘是從整個 vectorstore 生成的，取幾個代表性片段作為來源
            book_docs = []
            if engine.vectorstore:
                try:
                    book_docs = engine.vectorstore.similarity_search(
                        daily_insight[:100],  # 用書摘前 100 字作為查詢
                        k=min(5, config.CHUNK_OVERLAP)  # 取少量片段即可
                    )
                except Exception:
                    pass  # 如果檢索失敗，仍然可以生成筆記，只是沒有來源標註

            render_obsidian_button(
                engine=st.session_state.obsidian_engine,
                content=daily_insight,
                docs=book_docs,
                topic="今日書摘",
                button_key="knowledge_page",
                label="🗒️ 將此書摘轉成 Obsidian 筆記"
            )