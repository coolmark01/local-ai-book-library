# -*- coding: utf-8 -*-
"""
知識圖譜與靈感探索頁面 (ui_visualization.py)
============================================
負責：
  1. Tab 1: Obsidian 知識思維圖譜（含圓點大小自訂、進度條與「⏹️ 終止分析」中斷按鈕）
  2. Tab 2: 今日書摘與隨機靈感（自動當日快取 + 一鍵複製 + 轉 Obsidian 靈感卡片）
"""

from datetime import datetime
import streamlit as st
import streamlit.components.v1 as components

from visualization import VisualizationEngine, DOMAIN_PRESETS
from obsidian_helper import render_obsidian_button, _render_copy_button


def render_visualization_page(engine, config):
    """渲染知識圖譜與靈感探索主頁面。"""
    st.subheader("🕸️ 知識思維圖譜與靈感探索")
    st.caption("視覺化探索書庫底層思維拓撲，或抽取今日隨機靈感金句。")

    if not engine.vectorstore:
        st.warning("⚠️ 向量資料庫尚未初始化，請先至「知識庫管理」上傳書籍。")
        st.stop()

    viz_engine = VisualizationEngine(engine.vectorstore)
    books_data = engine.get_book_list_with_chunk_counts()

    if not books_data or (isinstance(books_data, list) and len(books_data) > 0 and "error" in books_data[0]):
        st.info("目前書庫中無書籍資料，請先上傳書籍。")
        st.stop()

    available_sources = [b["source"] for b in books_data if "source" in b]
    source_to_filename = {b["source"]: b["filename"] for b in books_data if "source" in b}

    tab_graph, tab_insight = st.tabs([
        "🕸️ Obsidian 知識思維圖譜 (Graph View)",
        "💡 今日書摘與隨機靈感 (Daily Insights)"
    ])

    # ================================================================
    # Tab 1: 知識思維圖譜
    # ================================================================
    with tab_graph:
        if "active_graph_data" not in st.session_state:
            cached_data = viz_engine.load_cached_graph()
            st.session_state["active_graph_data"] = cached_data

        with st.form(key="graph_generation_form"):
            col_dom1, col_dom2 = st.columns([2, 3])

            with col_dom1:
                domain_options = list(DOMAIN_PRESETS.keys()) + ["🔍 自訂焦點關鍵字"]
                selected_domain = st.selectbox(
                    "🎯 選擇圖譜思維導向 (Domain Lens)",
                    options=domain_options,
                    index=0,
                    help="選擇主題後，系統將以此領域的核心架構為主軸。"
                )

            with col_dom2:
                custom_anchors = st.text_input(
                    "輸入自訂焦點關鍵字 (逗號分隔)",
                    value="經濟, 投資, 短線, 長線, 基本價值, 價值投資" if selected_domain == "🔍 自訂焦點關鍵字" else "",
                    placeholder="例如：通膨, 利率, 資產配置, 安全邊際, 護城河",
                    help="若選擇「自訂焦點關鍵字」，請在此輸入核心詞彙。"
                )

            c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
            with c1:
                selected_sources = st.multiselect(
                    "📚 篩選納入書籍",
                    options=available_sources,
                    default=available_sources,
                    format_func=lambda s: f"📖 {source_to_filename.get(s, s)}"
                )
            with c2:
                max_concepts = st.slider("概念節點上限", 20, 100, 45, 5)
            with c3:
                min_weight = st.slider("共現強度門檻", 1, 5, 1, 1)
            with c4:
                # 👈 圓點基準尺寸滑桿
                base_node_size = st.slider("圓點大小", 14, 42, 24, 2, help="調整圖譜中所有節點圓點的基準尺寸大小。")

            btn_run_graph = st.form_submit_button("🚀 開始分析並更新知識圖譜", type="primary", use_container_width=True)

        # 執行生成與即時中斷處理
        if btn_run_graph:
            progress_bar = st.progress(0.0)
            status_text = st.empty()
            cancel_placeholder = st.empty()

            st.session_state["graph_cancel_requested"] = False

            # 終止按鈕
            if cancel_placeholder.button("⏹️ 終止圖譜分析", key="btn_cancel_graph", type="secondary", use_container_width=True):
                st.session_state["graph_cancel_requested"] = True

            def progress_callback(progress_val: float, message: str) -> bool:
                progress_bar.progress(min(progress_val, 1.0))
                status_text.markdown(f"**分析進度**：`{message}`")
                # 檢查終止信號
                if st.session_state.get("graph_cancel_requested", False):
                    return False
                return True

            graph_res = viz_engine.build_knowledge_graph(
                domain_name=selected_domain,
                custom_anchors=custom_anchors,
                max_concepts=max_concepts,
                min_edge_weight=min_weight,
                selected_sources=selected_sources,
                base_node_size=base_node_size,
                progress_callback=progress_callback
            )

            progress_bar.empty()
            status_text.empty()
            cancel_placeholder.empty()

            if graph_res.get("stats", {}).get("aborted"):
                st.warning("⚠️ 已終止圖譜生成作業。")
            elif graph_res.get("nodes"):
                st.session_state["active_graph_data"] = graph_res
                st.success("✅ 圖譜更新完成並已寫入本地快取！")
                st.rerun()

        # 渲染圖譜
        current_graph = st.session_state.get("active_graph_data")

        if current_graph and current_graph.get("nodes"):
            stats = current_graph.get("stats", {})

            col_s1, col_s2, col_s3, col_s4 = st.columns(4)
            col_s1.metric("涵蓋書籍", f"{stats.get('total_books', 0)} 本")
            col_s2.metric("核心概念節點", f"{stats.get('total_concepts', 0)} 個")
            col_s3.metric("關聯網絡連線", f"{stats.get('total_edges', 0)} 條")
            col_s4.metric("跨書樞紐/核心錨點", f"{stats.get('total_hubs', 0)} 個")

            st.markdown("<div style='height: 6px;'></div>", unsafe_allow_html=True)

            html_content = viz_engine.generate_vis_html(current_graph, height="600px")
            components.html(html_content, height=620, scrolling=False)

            g_tab_hubs, g_tab_export = st.tabs([
                "🌟 跨書知識樞紐 (Bridge Hubs)",
                "💾 匯出至 Obsidian 白板 (.canvas) / HTML"
            ])

            with g_tab_hubs:
                hubs = current_graph.get("hubs", [])
                if hubs:
                    st.markdown("#### 🔗 跨書貫通思維樞紐與核心錨點")
                    num_cols = 2
                    h_cols = st.columns(num_cols)
                    for idx, hub in enumerate(hubs):
                        target_col = h_cols[idx % num_cols]
                        with target_col:
                            with st.container(border=True):
                                tag = "🎯 核心主題錨點" if hub.get("is_anchor") else "🔄 跨書思維樞紐"
                                st.markdown(f"**[[{hub['concept']}]]** &nbsp; `{tag}` &nbsp; `加權 {hub['total_freq']}`")
                                books_formatted = "、".join([f"《{b}》" for b in hub["books"]])
                                st.caption(f"關聯書籍：{books_formatted if books_formatted else '全書庫概念'}")
                else:
                    st.info("目前條件下未偵測到跨書樞紐。")

            with g_tab_export:
                col_exp1, col_exp2 = st.columns(2)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

                with col_exp1:
                    canvas_json = viz_engine.generate_obsidian_canvas(current_graph)
                    st.download_button(
                        label="⬇️ 下載 Obsidian 原生 Canvas 白板檔 (.canvas)",
                        data=canvas_json,
                        file_name=f"Obsidian_ConceptGraph_{timestamp}.canvas",
                        mime="application/json",
                        type="primary",
                        use_container_width=True
                    )

                with col_exp2:
                    st.download_button(
                        label="⬇️ 下載獨立 HTML 互動圖譜 (.html)",
                        data=html_content,
                        file_name=f"Interactive_Graph_{timestamp}.html",
                        mime="text/html",
                        use_container_width=True
                    )
        else:
            st.info("💡 目前尚無生成的圖譜快取，請在上方設定條件後點擊「🚀 開始分析並更新知識圖譜」。")

    # ================================================================
    # Tab 2: 今日書摘與隨機靈感 (Daily Insights)
    # ================================================================
    with tab_insight:
        st.markdown("### 💡 今日黃金思想卡片")
        st.caption("AI 自動研讀書庫，提煉具備穿透力的核心金句、底層思維解讀與行動啟發。每日自動快取，亦可隨時抽換。")

        col_in1, col_in2 = st.columns([3, 1])
        with col_in1:
            target_insight_source = st.selectbox(
                "指定書籍範圍 (預設全書庫隨機)",
                options=["全庫隨機抽取"] + available_sources,
                format_func=lambda s: "🎲 全庫隨機抽取" if s == "全庫隨機抽取" else f"📖 {source_to_filename.get(s, s)}"
            )
        with col_in2:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            force_refresh = st.button("🎲 重新抽取今日靈感", use_container_width=True)

        selected_src = None if target_insight_source == "全庫隨機抽取" else target_insight_source

        with st.spinner("AI 正在提煉靈感金句與思維模型..."):
            insight_result = viz_engine.generate_daily_insight(
                llm=engine.llm,
                target_source=selected_src,
                force_refresh=force_refresh
            )

        if insight_result.get("status") == "success":
            insight_content = insight_result.get("content", "")
            insight_docs = insight_result.get("docs", [])

            with st.container(border=True):
                st.markdown(insight_content)

            st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
            col_cp, col_ob = st.columns([1, 1])

            with col_cp:
                _render_copy_button(insight_content, button_id="daily_insight_copy")

            with col_ob:
                if "obsidian_engine" not in st.session_state:
                    from obsidian_engine import ObsidianEngine
                    st.session_state.obsidian_engine = ObsidianEngine(llm=engine.llm)

                render_obsidian_button(
                    engine=st.session_state.obsidian_engine,
                    content=insight_content,
                    docs=insight_docs,
                    topic=f"今日靈感書摘 - {insight_result.get('date')}",
                    button_key="obs_daily_insight",
                    label="📝 轉成 Obsidian 靈感卡片",
                    note_type="atomic",
                    custom_tags=["今日靈感", "金句卡片", "每日書摘"]
                )
        else:
            st.error(f"獲取書摘失敗：{insight_result.get('content')}")