# -*- coding: utf-8 -*-
"""
Obsidian 筆記生成頁面 (ui_obsidian.py)
========================================
負責：
  1. 4 種專業筆記模式選擇（單書精讀、多書綜整、原子卡片、批判思維）
  2. 靈感快速膠囊 (Prompt Pills) 降低主題思考成本
  3. 書籍精準篩選與自訂標籤
  4. 產出 Markdown 筆記並支援一鍵複製與 .md 檔案下載
"""

import re
import html
from datetime import datetime
import streamlit as st
import streamlit.components.v1 as components

from obsidian_engine import ObsidianEngine


def _render_copy_button(text_content: str, button_id: str):
    """渲染免跳轉的一鍵複製剪貼簿按鈕。"""
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


def render_obsidian_page(engine, config):
    """渲染 Obsidian 知識筆記生成器專屬頁面。"""
    st.subheader("📝 Obsidian 知識筆記生成器")
    st.caption("支援單書精讀深度申論、多書交叉綜整、原子概念卡片 (Zettelkasten) 及批判性書評剖析。")

    if not engine.vectorstore:
        st.warning("⚠️ 向量資料庫未初始化，請確認系統狀態。")
        st.stop()

    books_data = engine.get_book_list_with_chunk_counts()
    if not books_data or (isinstance(books_data, list) and len(books_data) > 0 and "error" in books_data[0]):
        st.warning("⚠️ 目前書庫為空。請先至「知識庫管理」頁面上傳書籍。")
        st.stop()

    available_sources = [b["source"] for b in books_data if "source" in b]
    source_to_filename = {b["source"]: b["filename"] for b in books_data if "source" in b}

    if not available_sources:
        st.info("書庫中尚無可用書籍資料。")
        st.stop()

    st.divider()

    # 1. 筆記模式定義
    mode_options = {
        "📘 單書精讀 / 深度申論": {
            "type": "deep_dive",
            "desc": "深入剖析單一著作的論證脈絡、底層邏輯、關鍵章節與實踐落地步驟。",
            "placeholder": "例如：《劉慈欣談科幻》中關於科幻文學核心魅力與宏大敘事的底層思維",
            "suggest_single": True,
            "pills": ["🧠 核心論證體系拆解", "📑 關鍵章節深度導讀", "🎯 行動清單與日常實踐", "💎 金句本質與哲學啟示"]
        },
        "🌐 多書交叉 / 主題綜整": {
            "type": "synthesis",
            "desc": "交叉比對不同作者在同一主題上的共識、互補觀點與理論分歧。",
            "placeholder": "例如：不同著作中關於「習慣養成與認知重塑」的理論對話與共識",
            "suggest_single": False,
            "pills": ["🔄 觀點碰撞與分歧對比", "💡 跨學科底層共識", "🛠️ 綜合應用解決方案", "🧭 未來延伸探索路徑"]
        },
        "💡 原子概念卡片 (Zettelkasten)": {
            "type": "atomic",
            "desc": "提煉單一核心概念，給出高濃度本質定義、運作機制與關聯網絡。",
            "placeholder": "例如：卡片筆記法 (Zettelkasten) 的雙向連結核心機制",
            "suggest_single": False,
            "pills": ["⚙️ 運作機制與心理原理", "🛠️ 實踐應用場景", "⚠️ 常見認知盲點", "🔗 上下位關聯網絡"]
        },
        "⚖️ 批判性思維 / 觀點檢視": {
            "type": "critique",
            "desc": "檢驗特定論點的適用邊界、潛在盲點、未被言說的假設與辯證反思。",
            "placeholder": "例如：批判性剖析《金錢超思考》中財富思維的實踐盲點與前提條件",
            "suggest_single": False,
            "pills": ["⚠️ 潛在盲點與失效邊界", "🌟 理論突破與核心貢獻", "🔄 對立學派觀點對照", "🧪 實證檢驗與局限"]
        },
    }

    selected_mode_label = st.selectbox(
        "🎯 選擇筆記產出模式",
        options=list(mode_options.keys()),
        index=0
    )

    current_mode_info = mode_options[selected_mode_label]
    st.info(f"💡 **模式說明**：{current_mode_info['desc']}")

    # 靈感膠囊 (Prompt Pills) 點擊區
    st.caption("✨ **點擊下方靈感膠囊快速代入分析角度**：")
    pill_cols = st.columns(len(current_mode_info["pills"]))
    for idx, pill_text in enumerate(current_mode_info["pills"]):
        with pill_cols[idx]:
            if st.button(pill_text, key=f"pill_{idx}", use_container_width=True):
                st.session_state["obsidian_input_theme"] = f"{pill_text.split(' ')[1]}：探討..."

    # 2. 設定表單
    current_input_val = st.session_state.get("obsidian_input_theme", "")

    with st.form(key="obsidian_generator_form"):
        col1, col2 = st.columns([3, 2])
        with col1:
            theme = st.text_input(
                "📌 筆記主題 / 核心議題",
                value=current_input_val,
                placeholder=current_mode_info["placeholder"],
                help="輸入你想探討的核心議題、章節主題或概念名稱。"
            )
        with col2:
            custom_tags_input = st.text_input(
                "🏷️ 自訂標籤 (逗號分隔)",
                placeholder="思維模型, 認知科學, 讀書會",
                help="產出筆記 YAML Frontmatter 中的 tags 標籤。"
            )

        default_selection = [available_sources[0]] if current_mode_info["suggest_single"] and available_sources else available_sources

        selected_sources = st.multiselect(
            "📚 選擇關聯書籍（可複選）",
            options=available_sources,
            default=default_selection,
            format_func=lambda s: f"📖 {source_to_filename.get(s, s)}",
            help="單書精讀建議只選取 1 本目標書籍；多書綜整可複選多本書籍。"
        )

        submitted = st.form_submit_button("🚀 開始生成結構化 Obsidian 筆記", type="primary", use_container_width=True)

    # 3. 生成邏輯
    if submitted:
        if not theme.strip():
            st.error("請輸入筆記主題！")
            return
        if not selected_sources:
            st.error("請至少選擇一本書籍進行分析！")
            return

        with st.spinner(f"AI 正在研讀選定的 {len(selected_sources)} 本文獻，編撰【{selected_mode_label}】專題筆記..."):
            try:
                base_k = getattr(config, "FINAL_TOP_K", getattr(config, "TOP_K", 5))
                search_k = min(base_k * 3, 15)

                filter_dict = {"source": {"$in": selected_sources}} if len(selected_sources) < len(available_sources) else None
                retrieved_docs = engine.vectorstore.similarity_search(
                    theme,
                    k=search_k,
                    filter=filter_dict
                )

                if not retrieved_docs:
                    st.warning(f"在選定的書籍中未檢索到與「{theme}」相關的片段，請嘗試換個問法或放寬書籍選擇。")
                    return

                obsidian_engine = ObsidianEngine(llm=engine.llm)
                tags_list = [t.strip() for t in custom_tags_input.split(",") if t.strip()] if custom_tags_input else []

                result = obsidian_engine.generate_obsidian_note(
                    topic=theme,
                    docs=retrieved_docs,
                    note_type=current_mode_info["type"],
                    custom_tags=tags_list
                )

                if result["status"] == "success":
                    st.session_state["last_generated_obsidian_note"] = result["content"]
                    st.session_state["last_generated_obsidian_topic"] = theme
                    st.success("🎉 Obsidian 筆記生成成功！")
                else:
                    st.error(f"生成失敗：{result['content']}")

            except Exception as e:
                st.error(f"生成筆記過程發生異常：{e}")
                st.exception(e)

    # 4. 預覽與雙通道匯出
    if "last_generated_obsidian_note" in st.session_state and st.session_state["last_generated_obsidian_note"]:
        note_text = st.session_state["last_generated_obsidian_note"]
        current_topic = st.session_state.get("last_generated_obsidian_topic", "Obsidian_Note")

        st.divider()
        st.markdown("### 📄 筆記即時預覽")
        with st.expander("點擊展開 / 收合完整 Markdown 預覽", expanded=True):
            st.markdown(note_text)

        clean_topic = re.sub(r'[\\/*?:"<>| ]', '_', current_topic)[:30].strip('_')
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{clean_topic}_{timestamp}.md"

        c_copy, c_dl = st.columns([1, 1])
        with c_copy:
            _render_copy_button(note_text, button_id="obsidian_main_page")
        with c_dl:
            st.download_button(
                label="⬇️ 下載 .md 檔案至本地 Obsidian Vault",
                data=note_text,
                file_name=filename,
                mime="text/markdown",
                type="primary",
                use_container_width=True
            )