# -*- coding: utf-8 -*-
"""
知識庫管理頁面 (ui_manage.py)
==============================
負責：
  1. 📁 本地目錄掃描與書籍總清單 (支援 GUI 原生資料夾選取、子資料夾遍歷、去重與動態匯入狀態同步)
  2. 📥 單檔 / 批次檔案手動上傳
  3. 📖 已收錄書庫管理 (卡片 / 清單雙視圖與刪除確認)
  4. 📄 知識片段虛擬分頁瀏覽器
"""

import os
import logging
from datetime import datetime
from typing import Dict, Any, Tuple, List
import streamlit as st

from config import RAGConfig
from document_loader import process_and_store_document
from catalog_manager import CatalogManager

logger = logging.getLogger("LibraryLogger")


# ===================================================================
# 輔助函數：原生作業系統資料夾選取視窗 (GUI Dialog)
# ===================================================================
def _pick_directory_dialog() -> str:
    """彈出本地作業系統的原生選取資料夾對話框（Windows / macOS / Linux）。"""
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()  # 隱藏主視窗
        root.attributes('-topmost', True)  # 強制置頂顯示在瀏覽器前方
        folder_selected = filedialog.askdirectory(master=root, title="請選擇書籍存放資料夾")
        root.destroy()
        return os.path.abspath(folder_selected) if folder_selected else ""
    except Exception as e:
        logger.warning(f"[UI] 無法啟動 GUI 資料夾選取視窗: {e}")
        return ""


# ===================================================================
# 輔助函數：格式與品質徽章計算
# ===================================================================
def _get_quality_badge(book: Dict[str, Any]) -> Tuple[str, str, str]:
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
    st.caption("掃描本機目錄建立書籍清單、按需匯入私人書庫、檢視 OCR 品質並管理已收錄知識片段。")

    # 1. 處理延遲跳轉請求
    if "_jump_to_tab" in st.session_state:
        st.session_state["manage_active_tab"] = st.session_state.pop("_jump_to_tab")
    if "_jump_to_book" in st.session_state:
        st.session_state["chunk_book_selector"] = st.session_state.pop("_jump_to_book")

    tab_options = ["📁 本地目錄掃描與清單", "📥 上傳書籍檔案", "📖 已收錄書庫管理", "📄 知識片段瀏覽"]

    if "manage_active_tab" not in st.session_state or st.session_state["manage_active_tab"] not in tab_options:
        st.session_state["manage_active_tab"] = "📁 本地目錄掃描與清單"

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
    if selected_tab == "📁 本地目錄掃描與清單":
        _render_catalog_scan_section(engine, config)
    elif selected_tab == "📥 上傳書籍檔案":
        _render_upload_section(engine, config)
    elif selected_tab == "📖 已收錄書庫管理":
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
# 1. 本地目錄掃描與書籍總清單區塊 (含 GUI 瀏覽按鈕)
# ===================================================================
def _render_catalog_scan_section(engine, config: RAGConfig):
    """掃描本機資料夾建立總清單，支援 GUI 原生目錄選取、狀態雙向同步與按需批次入庫。"""
    st.markdown("### 📁 本地書籍目錄掃描與管理清單")
    st.caption("點擊「📂 瀏覽資料夾」直接選取本機目錄（系統將自動遞迴掃描所有子目錄），建立單一本機總目錄。掃描**不會立即匯入**向量資料庫，您可以隨後自由勾選入庫。")

    # 讀取並動態同步狀態
    raw_catalog = CatalogManager.load_catalog()
    db_books = engine.get_book_list_with_chunk_counts()
    if not (isinstance(db_books, list) and len(db_books) > 0 and "error" in db_books[0]):
        catalog = CatalogManager.sync_with_database(raw_catalog, db_books)
    else:
        catalog = raw_catalog

    # 初始化路徑狀態
    if "scan_folder_input" not in st.session_state:
        st.session_state["scan_folder_input"] = st.session_state.get("last_scan_path", "")

    # --------------------------------------------------------------- 掃描輸入區 (含 GUI 瀏覽按鈕)
    with st.container(border=True):
        col_dir, col_pick, col_btn = st.columns([3.2, 1.1, 1.2])
        
        with col_dir:
            scan_path = st.text_input(
                "書籍資料夾路徑",
                value=st.session_state["scan_folder_input"],
                placeholder="點擊右側「瀏覽」或手動輸入路徑...",
                help="系統會遞迴掃描此路徑下的所有子資料夾，收集 .pdf, .epub, .txt 檔案。"
            )
        
        with col_pick:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            if st.button("📂 瀏覽選取", use_container_width=True, help="彈出 Windows 資料夾選取視窗"):
                picked = _pick_directory_dialog()
                if picked:
                    st.session_state["scan_folder_input"] = picked
                    st.session_state["last_scan_path"] = picked
                    st.rerun()

        with col_btn:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            btn_scan = st.button("🔍 遞迴掃描", type="primary", use_container_width=True)

        target_scan_dir = scan_path.strip() or st.session_state["scan_folder_input"].strip()

        if btn_scan:
            if not target_scan_dir:
                st.warning("⚠️ 請先選取或輸入有效的本機資料夾路徑！")
            elif not os.path.exists(target_scan_dir):
                st.error(f"❌ 找不到路徑：`{target_scan_dir}`，請確認資料夾是否存在。")
            else:
                st.session_state["last_scan_path"] = target_scan_dir
                st.session_state["scan_folder_input"] = target_scan_dir
                try:
                    with st.spinner("AI 正在深層遍歷目錄結構與書籍檔案..."):
                        updated_cat, new_added, total_count = CatalogManager.scan_directory(target_scan_dir, catalog)
                        # 再次同步現有向量庫狀態
                        CatalogManager.sync_with_database(updated_cat, db_books)
                    st.success(f"🎉 掃描完成！新增發現 **{new_added}** 本新書籍，目前清單共收錄 **{total_count}** 本書。")
                    st.rerun()
                except Exception as e:
                    st.error(f"掃描過程發生錯誤: {e}")

    # --------------------------------------------------------------- 清單概覽統計
    total_books = len(catalog)
    imported_books = sum(1 for b in catalog.values() if b.get("is_imported", False))
    pending_books = total_books - imported_books

    st.markdown("<div style='height: 5px;'></div>", unsafe_allow_html=True)
    c_m1, c_m2, c_m3 = st.columns(3)
    c_m1.metric("📂 清單總收錄書籍", f"{total_books} 本")
    c_m2.metric("🟢 已匯入私人書庫", f"{imported_books} 本")
    c_m3.metric("⚪ 待匯入書籍", f"{pending_books} 本", delta=f"{pending_books} 待處理" if pending_books > 0 else None)

    if total_books == 0:
        st.info("💡 目前清單為空。請點擊上方「📂 瀏覽選取」選取您存放電子書的資料夾，再點擊「🔍 遞迴掃描」開始整理。")
        return

    st.divider()

    # --------------------------------------------------------------- 篩選與搜尋工具列
    f_col1, f_col2, f_col3 = st.columns([1.5, 2, 1.5])
    with f_col1:
        status_filter = st.selectbox(
            "匯入狀態篩選",
            options=["全部書籍", "僅顯示未匯入 (待處理)", "僅顯示已匯入"],
            index=0
        )
    with f_col2:
        search_kw = st.text_input("🔍 搜尋書名或資料夾關鍵字", placeholder="輸入書名關鍵字篩選...").strip().lower()
    with f_col3:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        if st.button("🧹 清理不存在的遺失檔案", use_container_width=True):
            catalog, removed_count = CatalogManager.clean_missing_files(catalog)
            st.success(f"已清理 {removed_count} 筆已從本機磁碟移除的檔案記錄。")
            st.rerun()

    # 過濾書籍列表
    filtered_items: List[Tuple[str, Dict[str, Any]]] = []
    for p, info in catalog.items():
        fname = info.get("filename", "").lower()
        folder = info.get("folder", "").lower()
        is_imp = info.get("is_imported", False)

        # 狀態過濾
        if status_filter == "僅顯示未匯入 (待處理)" and is_imp:
            continue
        if status_filter == "僅顯示已匯入" and not is_imp:
            continue

        # 關鍵字過濾
        if search_kw and (search_kw not in fname and search_kw not in folder):
            continue

        filtered_items.append((p, info))

    st.markdown(f"**符合條件的書籍**（共 **{len(filtered_items)}** 本）：")

    # --------------------------------------------------------------- 批次入庫操作列
    action_box = st.container(border=True)
    with action_box:
        ac1, ac2 = st.columns([3, 2])
        with ac1:
            st.markdown("##### 🚀 批次入庫作業")
            st.caption("選取下方書籍後點擊按鈕，系統將自動解析、OCR 辨識並向量化存入私人知識庫。")
        with ac2:
            btn_import_all_pending = st.button("⚡ 一鍵匯入所有「未匯入」書籍", type="primary", use_container_width=True)

    # --------------------------------------------------------------- 書籍清單表格渲染
    # 標題列
    h1, h2, h3, h4, h5, h6 = st.columns([0.6, 3.5, 1.2, 1.8, 1.2, 1.7])
    with h1:
        select_all = st.checkbox("全選", key="chk_select_all_catalog", help="選取目前畫面上顯示的所有書籍")
    with h2:
        st.markdown("**書籍名稱與路徑**")
    with h3:
        st.markdown("**格式 / 大小**")
    with h4:
        st.markdown("**所屬子目錄**")
    with h5:
        st.markdown("**庫藏狀態**")
    with h6:
        st.markdown("**單本操作**")

    st.markdown("<hr style='margin: 4px 0; border-top: 1px solid rgba(255,255,255,0.15);'>", unsafe_allow_html=True)

    selected_paths = []

    for path, info in filtered_items:
        fname = info.get("filename", "")
        ftype = info.get("file_type", "")
        fsize = info.get("file_size_mb", 0.0)
        folder = info.get("folder", ".")
        is_imp = info.get("is_imported", False)
        chunk_count = info.get("chunk_count", 0)

        safe_id = "".join(c for c in path if c.isalnum())[-16:]
        chk_key = f"chk_book_{safe_id}"

        c1, c2, c3, c4, c5, c6 = st.columns([0.6, 3.5, 1.2, 1.8, 1.2, 1.7])

        with c1:
            default_val = select_all if not is_imp else False
            is_checked = st.checkbox("", value=default_val, key=chk_key, label_visibility="collapsed")
            if is_checked:
                selected_paths.append(path)

        with c2:
            st.markdown(f"📖 **{fname}**")
            st.caption(f"`{path}`")

        with c3:
            st.caption(f"`{ftype}` &nbsp;|&nbsp; `{fsize} MB`")

        with c4:
            st.caption(f"📁 `{folder}`")

        with c5:
            if is_imp:
                st.markdown(f"🟢 **已匯入**")
                st.caption(f"(`{chunk_count}` 片段)")
            else:
                st.markdown("⚪ **未匯入**")

        with c6:
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                if not is_imp:
                    if st.button("📥", key=f"btn_single_imp_{safe_id}", help="將此單本書籍匯入私人知識庫"):
                        _execute_batch_ingest(engine, config, [path], catalog)
                else:
                    if st.button("🔍", key=f"btn_single_view_{safe_id}", help="前往瀏覽知識片段"):
                        st.session_state["_jump_to_book"] = fname
                        st.session_state["_jump_to_tab"] = "📄 知識片段瀏覽"
                        st.rerun()
            with col_b2:
                if st.button("❌", key=f"btn_remove_rec_{safe_id}", help="從清單中移除此記錄 (不刪除本機實體檔案)"):
                    CatalogManager.remove_item(path, catalog)
                    st.rerun()

        st.markdown("<hr style='margin: 2px 0; border-top: 1px solid rgba(255,255,255,0.06);'>", unsafe_allow_html=True)

    # --------------------------------------------------------------- 觸發批次匯入
    if selected_paths:
        with action_box:
            if st.button(f"🚀 匯入選取的 {len(selected_paths)} 本書籍至私人書庫", type="primary", use_container_width=True):
                _execute_batch_ingest(engine, config, selected_paths, catalog)

    if btn_import_all_pending:
        all_pending_paths = [p for p, info in catalog.items() if not info.get("is_imported", False)]
        if not all_pending_paths:
            st.info("目前所有書籍皆已成功匯入知識庫！")
        else:
            _execute_batch_ingest(engine, config, all_pending_paths, catalog)


def _execute_batch_ingest(engine, config: RAGConfig, file_paths: List[str], catalog: Dict[str, Dict[str, Any]]):
    """執行批次解析、切塊與向量化入庫管線。"""
    if not file_paths:
        return

    progress_bar = st.progress(0.0)
    status_placeholder = st.empty()
    total_files = len(file_paths)
    success_count = 0
    fail_count = 0
    total_created_chunks = 0

    for idx, fpath in enumerate(file_paths, start=1):
        if not os.path.exists(fpath):
            st.error(f"檔案不存在，跳過：`{fpath}`")
            fail_count += 1
            continue

        fname = os.path.basename(fpath)
        status_placeholder.markdown(f"**正在處理 ({idx}/{total_files})**：`{fname}`")

        def progress_callback(step: int, total_steps: int, msg: str):
            base_progress = (idx - 1) / total_files
            step_progress = (step / total_steps) * (1.0 / total_files)
            progress_bar.progress(min(base_progress + step_progress, 0.99))
            status_placeholder.text(f"[{idx}/{total_files}] {fname} -> {msg}")

        try:
            chunks = process_and_store_document(
                file_path=fpath,
                filename=fname,
                config=config,
                progress_callback=progress_callback
            )
            total_created_chunks += chunks
            success_count += 1

            # 更新 catalog 狀態
            if fpath in catalog:
                catalog[fpath]["is_imported"] = True
                catalog[fpath]["chunk_count"] = chunks
                catalog[fpath]["imported_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            logger.info(f"[Catalog Ingest] 匯入成功: {fname}, 新增 {chunks} chunks")
        except Exception as e:
            fail_count += 1
            logger.error(f"[Catalog Ingest] 匯入失敗: {fname}, 錯誤: {e}", exc_info=True)
            st.error(f"❌ 《{fname}》處理失敗：{e}")

    progress_bar.progress(1.0)
    status_placeholder.empty()

    CatalogManager.save_catalog(catalog)

    if success_count > 0:
        engine.rebuild_bm25()
        st.success(f"🎉 批次入庫完成！成功匯入 {success_count} 本書籍（合計新增 {total_created_chunks} 個知識片段），失敗 {fail_count} 本。")
        st.rerun()


# ===================================================================
# 2. 單檔/批次手動上傳區塊
# ===================================================================
def _render_upload_section(engine, config: RAGConfig):
    """手動上傳書籍與即時匯入處理。"""
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
                except Exception as e:
                    fail_count += 1
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
                st.session_state["_jump_to_tab"] = "📖 已收錄書庫管理"
                st.rerun()


# ===================================================================
# 3. 書庫管理區塊：支援清單與卡片視圖切換
# ===================================================================
def _render_book_management_section(engine):
    """已收錄書籍管理：提供卡片與清單視圖切換、品質評分與刪除。"""
    st.markdown("### 📖 已收錄書籍管理")

    books = engine.get_book_list_with_chunk_counts()

    if not books or (isinstance(books, list) and len(books) > 0 and "error" in books[0]):
        st.info("知識庫中目前沒有任何書籍。請先前往「📁 本地目錄掃描與清單」或「📥 上傳書籍檔案」匯入文獻。")
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
    """卡片網格視圖。"""
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
                    st.warning(f"⚠️ 確定要從知識庫刪除《{filename}》嗎？（總目錄清單會保留並自動標記為未匯入）")
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
    """緊湊清單視圖。"""
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
                if st.button("🗑️", key=f"btn_{del_key}", help="從書庫刪除此書籍"):
                    st.session_state[del_key] = True
                    st.rerun()

        if st.session_state.get(del_key, False):
            with st.container(border=True):
                st.warning(f"⚠️ 確定要從知識庫刪除《{filename}》嗎？（總目錄清單會保留並自動恢復為未匯入）")
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
# 4. 知識片段分頁瀏覽區塊
# ===================================================================
def _render_chunk_browser_section(engine):
    """分頁檢視選定書籍的知識片段。"""
    st.markdown("### 📄 知識片段瀏覽器")

    books = engine.get_book_list_with_chunk_counts()
    if not books or (isinstance(books, list) and len(books) > 0 and "error" in books[0]):
        st.info("目前書庫為空，無可用片段。")
        return

    book_map = {b["filename"]: b["source"] for b in books if "source" in b}
    book_options = list(book_map.keys())

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

    for i, chunk in enumerate(page_chunks, start=start_idx + 1):
        meta = chunk.get("metadata", {})
        chapter = meta.get("chapter", "")
        title_display = f"📌 片段 #{i}" + (f" — 《{chapter}》" if chapter else "")

        with st.expander(title_display, expanded=False):
            st.caption(f"來源檔名: `{meta.get('filename', selected_filename)}`")
            st.markdown(chunk.get("content", ""))