# -*- coding: utf-8 -*-
"""
知識庫管理頁面 (ui_manage.py)
==============================
負責：
  1. 多檔案上傳與即時向量化進度展示
  2. 狀態分頁導航（透過延遲狀態安全切換分頁與選定書籍）
  3. 書庫管理視圖切換：支援「🗂️ 卡片網格」與「📋 緊湊清單」兩種檢視模式
  4. 檔案格式、OCR 品質評分燈號、知識片段統計與獨立刪除確認
  5. 全庫清空危險操作防護
  6. 知識片段分頁瀏覽器 (虛擬化分頁展示)
"""

import os
import logging
from typing import Dict, Any, Tuple, List
import streamlit as st

from config import RAGConfig
from document_loader import process_and_store_document

logger = logging.getLogger("LibraryLogger")


# ===================================================================
# 輔助函數：格式與品質徽章計算
# ===================================================================
def _get_quality_badge(book: Dict[str, Any]) -> Tuple[str, str, str]:
    """
    回傳 (品質等級燈號, 評分文字, 提示訊息)。
    等級包含：good (優良), fair (普通), poor (差/需重新掃描), native (數位原生)
    """
    file_type = book.get("file_type", "unknown").lower()
    ocr_quality = book.get("ocr_quality", 0) or 0

    if file_type == "pdf":
        if ocr_quality >= 80:
            return "🟢", f"OCR: {ocr_quality}分 (優良)", "文字清晰，向量化檢索精準度高"
        elif ocr_quality >= 60:
            return "🟡", f"OCR: {ocr_quality}分 (良好)", "多數文字正常，可能存在少量排版錯字"
        elif ocr_quality >= 40:
            return "🟠", f"OCR: {ocr_quality}分 (普通)", "辨識品質一般，建議抽查關鍵片段"
        elif ocr_quality > 0:
            return "🔴", f"OCR: {ocr_quality}分 (偏低)", "辨識品質偏低，建議重新掃描或改用更清晰之 PDF"
        else:
            return "📄", "數位原生 / 歷史入庫", "內嵌純文字格式，無需進行光學文字辨識"
    elif file_type == "epub":
        return "📖", "數位 EPUB (優良)", "結構化電子書格式，排版解析完整"
    elif file_type == "txt":
        return "📝", "純文字 TXT", "純文字格式，直接完成向量切塊"
    else:
        return "📎", "未知格式", "未識別之文件格式"


# ===================================================================
# 主頁面入口
# ===================================================================
def render_manage_page(engine, config: RAGConfig):
    """渲染知識庫管理主頁面。"""
    st.subheader("📚 知識庫管理中心")
    st.caption("管理您的私人書庫：上傳文獻、檢視 OCR 識別品質、切換清單/卡片視圖並瀏覽分塊片段。")

    # 1. 處理延遲跳轉請求（必須在 widget 實例化前完成賦值）
    if "_jump_to_tab" in st.session_state:
        st.session_state["manage_active_tab"] = st.session_state.pop("_jump_to_tab")
    if "_jump_to_book" in st.session_state:
        st.session_state["chunk_book_selector"] = st.session_state.pop("_jump_to_book")

    tab_options = ["📥 上傳書籍", "📖 書庫管理", "📄 知識片段瀏覽"]

    # 初始化導航狀態
    if "manage_active_tab" not in st.session_state or st.session_state["manage_active_tab"] not in tab_options:
        st.session_state["manage_active_tab"] = "📖 書庫管理"

    # 2. 渲染導航分頁 Widget
    selected_tab = st.radio(
        "分頁導航",
        options=tab_options,
        horizontal=True,
        label_visibility="collapsed",
        key="manage_active_tab"
    )

    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

    # 3. 根據選中狀態渲染對應區塊
    if selected_tab == "📥 上傳書籍":
        _render_upload_section(engine, config)
    elif selected_tab == "📖 書庫管理":
        _render_book_management_section(engine)
    elif selected_tab == "📄 知識片段瀏覽":
        _render_chunk_browser_section(engine)

    # 側邊欄即時日誌
    with st.sidebar.expander("📄 即時系統 Log", expanded=False):
        if st.button("🔄 刷新 Log", use_container_width=True):
            st.rerun()
        log_path = os.path.join("logs", "app.log")
        if os.path.exists(log_path):
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                st.code("".join(lines[-80:]), language="text")
            except Exception as e:
                st.error(f"讀取 Log 失敗: {e}")
        else:
            st.info("尚無記錄日誌。")


# ===================================================================
# 1. 上傳書籍區塊
# ===================================================================
def _render_upload_section(engine, config: RAGConfig):
    """上傳書籍與即時匯入進度處理。"""
    st.markdown("### 📥 上傳文獻檔案")
    st.caption("支援 **PDF**（含掃描件自動 OCR 辨識）、**EPUB**（非標準格式具備 ZIP 容錯）、**TXT**。")

    uploaded_files = st.file_uploader(
        "選擇要匯入的書籍檔案（可多選）",
        type=["pdf", "epub", "txt"],
        accept_multiple_files=True,
        key="uploader_widget"
    )

    if uploaded_files:
        st.info(f"已選取 **{len(uploaded_files)}** 個檔案，點擊下方按鈕開始處理。")

        if st.button("🚀 開始批次解析並存入知識庫", type="primary", use_container_width=True):
            progress_bar = st.progress(0.0)
            status_placeholder = st.empty()
            total_files = len(uploaded_files)
            total_created_chunks = 0
            success_count = 0
            fail_count = 0

            for idx, uploaded_file in enumerate(uploaded_files, start=1):
                filename = uploaded_file.name
                temp_path = os.path.join(config.UPLOAD_DIR, filename)

                status_placeholder.markdown(f"**處理中 ({idx}/{total_files})**：`{filename}`")

                with open(temp_path, "wb") as fh:
                    fh.write(uploaded_file.getbuffer())

                def progress_callback(step: int, total_steps: int, msg: str):
                    base_progress = (idx - 1) / total_files
                    step_progress = (step / total_steps) * (1.0 / total_files)
                    progress_bar.progress(min(base_progress + step_progress, 0.99))
                    status_placeholder.text(f"[{idx}/{total_files}] {filename} -> {msg}")

                try:
                    chunks = process_and_store_document(
                        file_path=temp_path,
                        filename=filename,
                        config=config,
                        progress_callback=progress_callback
                    )
                    total_created_chunks += chunks
                    success_count += 1
                    logger.info(f"[UI_MANAGE] 上傳成功: {filename}, 新增 {chunks} chunks")
                except Exception as e:
                    fail_count += 1
                    logger.error(f"[UI_MANAGE] 上傳失敗: {filename}, 錯誤: {e}", exc_info=True)
                    st.error(f"❌ 《{filename}》處理失敗：{e}")
                finally:
                    if os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except Exception:
                            pass

            progress_bar.progress(1.0)
            status_placeholder.empty()

            if success_count > 0:
                engine.rebuild_bm25()
                st.success(f"🎉 匯入完成！成功收錄 {success_count} 本（新增 {total_created_chunks} 個知識片段），失敗 {fail_count} 本。")
                st.session_state["_jump_to_tab"] = "📖 書庫管理"
                st.rerun()
            else:
                st.error("所有檔案匯入失敗，請檢查檔案格式或系統日誌。")

    st.divider()
    st.markdown("### 📊 書庫收錄概覽")
    stats = engine.get_library_stats()
    if "error" not in stats:
        c1, c2 = st.columns(2)
        c1.metric("總收錄書籍數", f"{stats['book_count']} 本")
        c2.metric("總知識片段數", f"{stats['total_chunks']} 筆")
    else:
        st.warning("無法取得書庫統計資訊。")


# ===================================================================
# 2. 書庫管理區塊：支援清單與卡片視圖切換
# ===================================================================
def _render_book_management_section(engine):
    """書庫管理主區塊：提供視圖模式切換（卡片 / 清單）。"""
    st.markdown("### 📖 已收錄書籍管理")

    books = engine.get_book_list_with_chunk_counts()

    if not books or (isinstance(books, list) and len(books) > 0 and "error" in books[0]):
        st.info("知識庫中目前沒有任何書籍。請先前往「📥 上傳書籍」分頁匯入文獻。")
        return

    total_chunks = sum(b.get("chunk_count", 0) for b in books)

    top_col1, top_col2 = st.columns([3, 1.2])
    with top_col1:
        st.caption(f"共收錄 **{len(books)}** 本書籍，合計 **{total_chunks}** 個知識片段。")
    with top_col2:
        view_mode = st.radio(
            "檢視模式",
            options=["🗂️ 卡片網格", "📋 緊湊清單"],
            index=1,
            horizontal=True,
            label_visibility="collapsed"
        )

    st.divider()

    if view_mode == "🗂️ 卡片網格":
        _render_card_grid_view(books, engine)
    else:
        _render_compact_list_view(books, engine)

    st.divider()
    with st.expander("⚠️ 危險管理區（清空所有數據）", expanded=False):
        st.markdown("**警告**：此操作將徹底清空向量資料庫中的所有書籍、知識片段及 BM25 索引，無法復原。")
        if not st.session_state.get("confirm_clear_all", False):
            if st.button("🗑️ 清空全庫資料", type="secondary"):
                st.session_state.confirm_clear_all = True
                st.rerun()
        else:
            st.error("🚨 請再次確認：是否要徹底清空所有知識庫資料？")
            col_cancel, col_confirm = st.columns(2)
            with col_cancel:
                if st.button("❌ 取消清空", key="cancel_clear_all", use_container_width=True):
                    st.session_state.confirm_clear_all = False
                    st.rerun()
            with col_confirm:
                if st.button("🔥 確定清空所有資料", key="do_clear_all", type="primary", use_container_width=True):
                    result = engine.clear_all_library_data()
                    st.session_state.confirm_clear_all = False
                    if result.get("status") == "success":
                        st.success(f"已清空知識庫，共刪除 {result.get('deleted_count', 0)} 筆片段。")
                    else:
                        st.error(f"清空失敗：{result.get('message', '未知錯誤')}")
                    st.rerun()


def _render_card_grid_view(books: List[Dict[str, Any]], engine):
    """卡片網格視圖 (Card Grid)。"""
    num_cols = 2
    cols = st.columns(num_cols)

    for i, book in enumerate(books):
        source = book.get("source", "")
        filename = book.get("filename", source)
        chunk_count = book.get("chunk_count", 0)
        file_type = book.get("file_type", "unknown").upper()

        badge_icon, quality_text, quality_tooltip = _get_quality_badge(book)
        safe_id = "".join(c for c in source if c.isalnum())[:20]
        del_key = f"del_confirm_{safe_id}"

        target_col = cols[i % num_cols]

        with target_col:
            with st.container(border=True):
                st.markdown(f"#### 📖 {filename}")

                info_c1, info_c2 = st.columns([1, 1])
                with info_c1:
                    st.caption(f"**格式**：`{file_type}` &nbsp;|&nbsp; **片段**：`{chunk_count} 筆`")
                with info_c2:
                    st.caption(f"**狀態**：{badge_icon} {quality_text}", help=quality_tooltip)

                st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
                btn_c1, btn_c2 = st.columns([1, 1])

                with btn_c1:
                    if st.button("🔍 瀏覽片段", key=f"btn_view_card_{safe_id}", use_container_width=True):
                        st.session_state["_jump_to_book"] = filename
                        st.session_state["_jump_to_tab"] = "📄 知識片段瀏覽"
                        st.rerun()

                with btn_c2:
                    if st.button("🗑️ 刪除本書", key=f"btn_del_card_{del_key}", use_container_width=True):
                        st.session_state[del_key] = True
                        st.rerun()

                if st.session_state.get(del_key, False):
                    st.warning(f"⚠️ 確定要刪除《{filename}》嗎？")
                    cb1, cb2 = st.columns([1, 1])
                    with cb1:
                        if st.button("❌ 取消", key=f"cancel_card_{del_key}", use_container_width=True):
                            st.session_state[del_key] = False
                            st.rerun()
                    with cb2:
                        if st.button("✅ 確定", key=f"exec_card_{del_key}", type="primary", use_container_width=True):
                            res = engine.delete_book_by_source(source)
                            st.session_state[del_key] = False
                            if res.get("status") == "success":
                                st.success(f"已成功刪除《{filename}》")
                            else:
                                st.error(f"刪除失敗：{res.get('message')}")
                            st.rerun()


def _render_compact_list_view(books: List[Dict[str, Any]], engine):
    """緊湊清單視圖 (Compact Table / List View)。"""
    h_col1, h_col2, h_col3, h_col4, h_col5 = st.columns([4, 1.2, 2.2, 1.5, 1.8])
    with h_col1:
        st.markdown("**書籍名稱**")
    with h_col2:
        st.markdown("**格式**")
    with h_col3:
        st.markdown("**品質狀態**")
    with h_col4:
        st.markdown("**片段數量**")
    with h_col5:
        st.markdown("**操作**")

    st.divider()

    for book in books:
        source = book.get("source", "")
        filename = book.get("filename", source)
        chunk_count = book.get("chunk_count", 0)
        file_type = book.get("file_type", "unknown").upper()

        badge_icon, quality_text, quality_tooltip = _get_quality_badge(book)
        safe_id = "".join(c for c in source if c.isalnum())[:20]
        del_key = f"del_confirm_list_{safe_id}"

        col1, col2, col3, col4, col5 = st.columns([4, 1.2, 2.2, 1.5, 1.8])

        with col1:
            st.markdown(f"📖 **{filename}**")
        with col2:
            st.caption(f"`{file_type}`")
        with col3:
            st.caption(f"{badge_icon} {quality_text}", help=quality_tooltip)
        with col4:
            st.caption(f"`{chunk_count} 筆`")
        with col5:
            action_c1, action_c2 = st.columns(2)
            with action_c1:
                if st.button("🔍", key=f"btn_view_list_{safe_id}", help="檢視此書知識片段"):
                    st.session_state["_jump_to_book"] = filename
                    st.session_state["_jump_to_tab"] = "📄 知識片段瀏覽"
                    st.rerun()
            with action_c2:
                if st.button("🗑️", key=f"btn_{del_key}", help="刪除此書籍"):
                    st.session_state[del_key] = True
                    st.rerun()

        if st.session_state.get(del_key, False):
            with st.container(border=True):
                st.warning(f"⚠️ 確定要從知識庫中刪除《{filename}》及其所有片段嗎？")
                cb1, cb2 = st.columns([1, 1])
                with cb1:
                    if st.button("❌ 取消", key=f"cancel_list_{del_key}", use_container_width=True):
                        st.session_state[del_key] = False
                        st.rerun()
                with cb2:
                    if st.button("✅ 確定刪除", key=f"exec_list_{del_key}", type="primary", use_container_width=True):
                        res = engine.delete_book_by_source(source)
                        st.session_state[del_key] = False
                        if res.get("status") == "success":
                            st.success(f"已成功刪除《{filename}》")
                        else:
                            st.error(f"刪除失敗：{res.get('message')}")
                        st.rerun()

        st.markdown("<hr style='margin: 4px 0; border: 0; border-top: 1px solid rgba(250,250,250,0.1);'>", unsafe_allow_html=True)


# ===================================================================
# 3. 知識片段分頁瀏覽區塊
# ===================================================================
def _render_chunk_browser_section(engine):
    """分頁檢視選定書籍的知識片段，防止一次性渲染大量 expander 卡死瀏覽器。"""
    st.markdown("### 📄 知識片段瀏覽器")

    books = engine.get_book_list_with_chunk_counts()
    if not books or (isinstance(books, list) and len(books) > 0 and "error" in books[0]):
        st.info("目前書庫為空，無可用片段。")
        return

    book_map = {b["filename"]: b["source"] for b in books if "source" in b}
    book_options = list(book_map.keys())

    # 確保 session_state 中的預設書籍有效
    if "chunk_book_selector" not in st.session_state or st.session_state["chunk_book_selector"] not in book_options:
        st.session_state["chunk_book_selector"] = book_options[0]

    selected_filename = st.selectbox(
        "選擇要檢視的書籍",
        options=book_options,
        key="chunk_book_selector"
    )

    if not selected_filename:
        return

    selected_source = book_map[selected_filename]
    chunks = engine.get_book_chunks(selected_source)

    if not chunks:
        st.info("此書籍目前無已索引的知識片段。")
        return

    total_chunks = len(chunks)
    PAGE_SIZE = 30
    total_pages = max((total_chunks + PAGE_SIZE - 1) // PAGE_SIZE, 1)

    page_key = f"page_idx_{selected_source}"
    if page_key not in st.session_state:
        st.session_state[page_key] = 0

    current_page = st.session_state[page_key]
    if current_page >= total_pages:
        current_page = 0
        st.session_state[page_key] = 0

    start_idx = current_page * PAGE_SIZE
    end_idx = min(start_idx + PAGE_SIZE, total_chunks)
    page_chunks = chunks[start_idx:end_idx]

    # 分頁導航列
    col_prev, col_info, col_next = st.columns([1, 3, 1])
    with col_prev:
        if current_page > 0:
            if st.button("◀ 上一頁", key=f"prev_btn_{selected_source}", use_container_width=True):
                st.session_state[page_key] -= 1
                st.rerun()
    with col_info:
        st.markdown(
            f"<div style='text-align: center; padding-top: 5px;'>"
            f"第 <b>{current_page + 1}</b> / <b>{total_pages}</b> 頁 "
            f"（顯示第 {start_idx + 1} ~ {end_idx} 筆，共 {total_chunks} 筆片段）"
            f"</div>",
            unsafe_allow_html=True
        )
    with col_next:
        if current_page < total_pages - 1:
            if st.button("下一頁 ▶", key=f"next_btn_{selected_source}", use_container_width=True):
                st.session_state[page_key] += 1
                st.rerun()

    st.divider()

    # 渲染選定書籍的片段
    for i, chunk in enumerate(page_chunks, start=start_idx + 1):
        meta = chunk.get("metadata", {})
        chapter = meta.get("chapter", "")
        title_display = f"📌 片段 #{i}" + (f" — 《{chapter}》" if chapter else "")

        with st.expander(title_display, expanded=False):
            st.caption(f"來源檔名: `{meta.get('filename', selected_filename)}`")
            st.markdown(chunk.get("content", ""))