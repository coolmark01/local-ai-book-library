# -*- coding: utf-8 -*-
"""
應用程式主入口 (app.py)
========================
負責：
  1. 初始化日誌系統與全域 Streamlit 頁面配置
  2. 載入並同步使用者動態設定 (settings.json -> RAGConfig)
  3. 管理 BookRAGEngine 全域實例生命週期與熱重啟機制
  4. 側邊欄導航路由：
     - 💬 智能書籍問答
     - 🕸️ 知識關聯圖譜
     - 📝 Obsidian 筆記
     - 🧠 第二大腦筆記庫
     - 📚 知識庫管理
     - ⚙️ 系統設定
"""

import os
import sys
import logging
import streamlit as st

from config import RAGConfig
from retrieval_engine import BookRAGEngine
from ui_settings import load_settings, _apply_settings_to_config

# ===================================================================
# 1. 系統日誌配置
# ===================================================================
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "app.log")

logger = logging.getLogger("LibraryLogger")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

# ===================================================================
# 2. 頁面基礎屬性配置
# ===================================================================
st.set_page_config(
    page_title="AI 私人書庫與知識作業系統",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ===================================================================
# 3. 引擎實例與設定生命週期管理
# ===================================================================
def init_or_get_engine() -> tuple[BookRAGEngine, RAGConfig]:
    """初始化或從 Session State 獲取 RAG 引擎與全域配置。"""
    if "config" not in st.session_state:
        config = RAGConfig()
        user_settings = load_settings()
        _apply_settings_to_config(user_settings, config)
        st.session_state.config = config
    else:
        config = st.session_state.config

    need_reinit = st.session_state.get("need_reinit", False)

    if "engine" not in st.session_state or need_reinit:
        with st.spinner("AI 知識庫引擎初始化 / 重新載入中..."):
            user_settings = load_settings()
            _apply_settings_to_config(user_settings, config)
            engine = BookRAGEngine(config=config)
            st.session_state.engine = engine
            st.session_state.need_reinit = False
            logger.info("[App] BookRAGEngine 已成功初始化")
    else:
        engine = st.session_state.engine

    return engine, config

engine, config = init_or_get_engine()

# ===================================================================
# 4. 側邊欄狀態與導航選單
# ===================================================================
with st.sidebar:
    st.title("📚 AI 私人書庫")
    st.caption("Local AI Second Brain OS")
    st.divider()

    # 導航選單（加入 第二大腦筆記庫）
    menu_options = [
        "💬 智能書籍問答",
        "🕸️ 知識關聯圖譜",
        "📝 Obsidian 筆記",
        "🧠 第二大腦筆記庫",
        "📚 知識庫管理",
        "⚙️ 系統設定"
    ]
    
    page = st.radio(
        "系統功能導航",
        options=menu_options,
        index=0,
        label_visibility="collapsed"
    )

    st.divider()

    # 引擎與計算裝置狀態指示
    st.markdown("### 🖥️ 運行狀態")
    if engine.is_ready:
        st.success("🟢 AI 核心已就緒")
    else:
        st.error("🔴 核心未就緒 (請檢查 LLM/資料庫)")

    device_label = "CUDA (GPU 加速)" if config.EMBEDDING_DEVICE == "cuda" else "CPU 模式"
    st.caption(f"**計算裝置**：`{device_label}`")
    st.caption(f"**語言模型**：`{config.MODEL_NAME}`")
    st.caption(f"**重排序模型**：`{config.RERANKER_MODEL_NAME.split('/')[-1] if config.USE_RERANKER else '未啟用'}`")

    # 即時書庫藏量
    stats = engine.get_library_stats()
    if "error" not in stats:
        st.caption(f"**庫藏規模**：{stats.get('book_count', 0)} 本書 / {stats.get('total_chunks', 0)} 個片段")

# ===================================================================
# 5. 路由分發渲染
# ===================================================================
if page == "💬 智能書籍問答":
    from ui_qa import render_qa_page
    render_qa_page(engine)

elif page == "🕸️ 知識關聯圖譜":
    from ui_visualization import render_visualization_page
    render_visualization_page(engine, config)

elif page == "📝 Obsidian 筆記":
    from ui_obsidian import render_obsidian_page
    render_obsidian_page(engine, config)

elif page == "🧠 第二大腦筆記庫":
    from ui_vault import render_vault_page
    render_vault_page()

elif page == "📚 知識庫管理":
    from ui_manage import render_manage_page
    render_manage_page(engine, config)

elif page == "⚙️ 系統設定":
    from ui_settings import render_settings_page
    render_settings_page(engine, config)