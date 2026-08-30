# -*- coding: utf-8 -*-
"""
設定與系統診斷頁面 (ui_settings.py)
===================================
負責：
  1. AI 模型配置（本地 Ollama / 雲端 API LLM）
  2. 計算裝置硬體切換（CUDA GPU 加速 / CPU 通用處理器）
  3. 情境預設檔 (Preset Profiles) 與進階兩階段檢索調校
  4. LLM 生成溫度、上下文視窗與切塊設定
  5. 系統環境與 GPU 加速狀態診斷
"""

import os
import sys
import json
import requests
import streamlit as st

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")


def load_settings() -> dict:
    """從 settings.json 讀取設定，若不存在則回傳完整預設值。"""
    defaults = {
        # 模型設定
        "llm_provider": "local",
        "ollama_base_url": "http://localhost:11434",
        "ollama_model": "",
        "cloud_provider": "OpenAI",
        "cloud_api_key": "",
        "cloud_model": "",
        "cloud_base_url": "",
        # 硬體計算裝置 (cuda / cpu)
        "compute_device": "cuda",
        # 預設檔與檢索參數
        "preset_profile": "⚖️ 日常平衡模式（推薦）",
        "use_reranker": True,
        "reranker_model": "BAAI/bge-reranker-v2-m3",
        "initial_retrieval_k": 15,
        "final_top_k": 5,
        # 生成與切塊參數
        "llm_temperature": 0.1,
        "max_context_tokens": 16384,
        "chunk_size": 400,
        "chunk_overlap": 60,
        "enable_s2t": True,
    }
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            defaults.update(saved)
        except Exception:
            pass
    return defaults


def save_settings(settings: dict):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def _apply_settings_to_config(settings: dict, config):
    # LLM 提供者與位址
    config.LLM_PROVIDER = settings.get("llm_provider", "local")
    if settings.get("ollama_base_url"):
        config.OLLAMA_BASE_URL = settings["ollama_base_url"]
    if settings.get("ollama_model"):
        config.MODEL_NAME = settings["ollama_model"]

    # 計算裝置 (CPU / CUDA)
    device = settings.get("compute_device", "cuda").lower()
    config.EMBEDDING_DEVICE = device
    config.RERANKER_DEVICE = device

    # 檢索與 Reranker
    config.USE_RERANKER = bool(settings.get("use_reranker", True))
    if settings.get("reranker_model"):
        config.RERANKER_MODEL_NAME = settings["reranker_model"]
    config.INITIAL_RETRIEVAL_K = int(settings.get("initial_retrieval_k", 15))
    config.FINAL_TOP_K = int(settings.get("final_top_k", 5))

    # 生成與切塊
    config.LLM_TEMPERATURE = float(settings.get("llm_temperature", 0.1))
    config.MAX_CONTEXT_TOKENS = int(settings.get("max_context_tokens", 16384))
    config.CHUNK_SIZE = int(settings.get("chunk_size", 400))
    config.CHUNK_OVERLAP = int(settings.get("chunk_overlap", 60))
    config.ENABLE_S2T = bool(settings.get("enable_s2t", True))


def _test_ollama_connection(url: str):
    try:
        clean_url = url.rstrip("/")
        resp = requests.get(f"{clean_url}/api/tags", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            models = data.get("models", [])
            model_names = [m.get("name", "?") for m in models]
            display = ", ".join(model_names[:6])
            if len(model_names) > 6:
                display += "..."
            st.success(f"✅ 連線成功！伺服器上有 {len(models)} 個可用模型：{display}")
        else:
            st.error(f"❌ 連線失敗，HTTP 狀態碼：{resp.status_code}")
    except Exception as e:
        st.error(f"❌ 連線異常：{e}")


def _get_model_placeholder(provider: str) -> str:
    placeholders = {
        "OpenAI": "gpt-4o / gpt-4o-mini",
        "Anthropic": "claude-3-5-sonnet-20241022",
        "Google Gemini": "gemini-1.5-pro / gemini-1.5-flash",
        "OpenAI 相容（自訂端點）": "deepseek-chat / qwen-plus",
    }
    return placeholders.get(provider, "model-id")


def render_settings_page(engine, config):
    st.subheader("⚙️ 系統設定與環境診斷")

    tab_preset, tab_model, tab_hardware, tab_advanced, tab_diag = st.tabs([
        "⚡ 情境預設模式",
        "🤖 AI 模型配置",
        "🖥️ 計算裝置 (CPU/CUDA)",
        "🛠️ 進階檢索與切塊調校",
        "🔍 硬體與 CUDA 診斷",
    ])

    settings = load_settings()

    # ================================================================
    # Tab 1: 情境預設模式 (Preset Profiles)
    # ================================================================
    with tab_preset:
        st.markdown("### ⚡ 一鍵情境模式切換")
        st.caption("根據當前的使用情境，一鍵套用經過最佳化的參數組合。")

        preset_options = [
            "⚡ 快速問答模式（極速回應）",
            "⚖️ 日常平衡模式（推薦）",
            "🔬 學術深度研究模式（高精準/長篇）",
            "🛠️ 自訂進階模式",
        ]
        curr_preset = settings.get("preset_profile", "⚖️ 日常平衡模式（推薦）")
        preset_idx = preset_options.index(curr_preset) if curr_preset in preset_options else 1

        selected_preset = st.radio(
            "選擇運行情境",
            options=preset_options,
            index=preset_idx,
            help="選擇情境後，點擊下方「套用並重啟」即可即時生效。"
        )

        preset_descriptions = {
            "⚡ 快速問答模式（極速回應）": "關閉 Reranker，初篩 10 筆直接選前 3 筆，適合純 CPU 或追求毫秒級回應速度。",
            "⚖️ 日常平衡模式（推薦）": "啟用 BGE-Reranker，初篩 15 筆精選 5 筆，平衡速度與精準度，適合大部分日常閱讀問答。",
            "🔬 學術深度研究模式（高精準/長篇）": "初篩 30 筆，經 Reranker 交叉評分精選 8 筆，生成溫度降至 0.05，適合多書對比與跨章節長篇綜整。",
            "🛠️ 自訂進階模式": "手動至「🛠️ 進階檢索與切塊調校」分頁自由調節所有參數。",
        }
        st.info(preset_descriptions[selected_preset])

        if st.button("🚀 套用此情境預設並重啟引擎", type="primary", use_container_width=True):
            settings["preset_profile"] = selected_preset
            if selected_preset == "⚡ 快速問答模式（極速回應）":
                settings["use_reranker"] = False
                settings["initial_retrieval_k"] = 10
                settings["final_top_k"] = 3
                settings["llm_temperature"] = 0.2
            elif selected_preset == "⚖️ 日常平衡模式（推薦）":
                settings["use_reranker"] = True
                settings["initial_retrieval_k"] = 15
                settings["final_top_k"] = 5
                settings["llm_temperature"] = 0.1
            elif selected_preset == "🔬 學術深度研究模式（高精準/長篇）":
                settings["use_reranker"] = True
                settings["initial_retrieval_k"] = 30
                settings["final_top_k"] = 8
                settings["llm_temperature"] = 0.05

            save_settings(settings)
            _apply_settings_to_config(settings, config)
            st.session_state.need_reinit = True
            st.session_state.settings_updated = True
            st.success(f"已切換至【{selected_preset}】！")
            st.rerun()

    # ================================================================
    # Tab 2: AI 模型設定
    # ================================================================
    with tab_model:
        st.markdown("### 🖥️ 本地 LLM 設定 (Ollama)")
        col1, col2 = st.columns([1, 1])
        with col1:
            ollama_url = st.text_input("Ollama 服務位址", value=settings.get("ollama_base_url", "http://localhost:11434"))
        with col2:
            ollama_model = st.text_input("本地語言模型名稱", value=settings.get("ollama_model", "") or config.MODEL_NAME)

        if st.button("🔌 測試 Ollama 連線", key="btn_test_ollama"):
            _test_ollama_connection(ollama_url)

        st.divider()
        st.markdown("### ☁️ 雲端 API LLM 設定")
        use_cloud = st.toggle("啟用雲端 API 模式", value=(settings.get("llm_provider") == "cloud"))

        cloud_provider = settings.get("cloud_provider", "OpenAI")
        cloud_api_key = settings.get("cloud_api_key", "")
        cloud_model = settings.get("cloud_model", "")
        cloud_base_url = settings.get("cloud_base_url", "")

        if use_cloud:
            c1, c2 = st.columns([1, 1])
            with c1:
                provider_list = ["OpenAI", "Anthropic", "Google Gemini", "OpenAI 相容（自訂端點）"]
                idx = provider_list.index(cloud_provider) if cloud_provider in provider_list else 0
                cloud_provider = st.selectbox("API 供應商", provider_list, index=idx)
            with c2:
                cloud_model = st.text_input("雲端模型名稱 (Model ID)", value=cloud_model, placeholder=_get_model_placeholder(cloud_provider))

            cloud_api_key = st.text_input("API Key / Token", value=cloud_api_key, type="password")
            if cloud_provider == "OpenAI 相容（自訂端點）":
                cloud_base_url = st.text_input("自訂 API Base URL", value=cloud_base_url, placeholder="https://api.deepseek.com/v1")

    # ================================================================
    # Tab 3: 計算裝置 (CPU / CUDA) 切換
    # ================================================================
    with tab_hardware:
        st.markdown("### 🖥️ 本地計算裝置切換 (Embedding & Reranker)")
        st.caption("設定文字向量化嵌入模型與 Cross-Encoder 重排序模型運行的計算裝置。")

        device_options = [
            "CUDA (NVIDIA 顯示卡加速 - 需安裝 CUDA 支援的 PyTorch)",
            "CPU (通用處理器 - 適用於無獨立顯卡 / AMD / Intel 顯卡設備)"
        ]
        curr_device_str = "CUDA" if settings.get("compute_device", "cuda").lower() == "cuda" else "CPU"
        device_idx = 0 if curr_device_str == "CUDA" else 1

        selected_device_option = st.radio(
            "選擇計算裝置",
            options=device_options,
            index=device_idx,
            help="若使用非 NVIDIA 顯示卡或 CUDA 發生相容性錯誤，請選擇 CPU 模式。"
        )

        target_device = "cuda" if "CUDA" in selected_device_option else "cpu"

        if target_device == "cuda":
            st.info("💡 **CUDA 模式**：利用 NVIDIA GPU 大幅加快書籍解析向量化與重排序評分速度。")
        else:
            st.warning("⚠️ **CPU 模式**：完全依賴中央處理器運行，相容性最高，但在處理大篇幅書籍向量化時耗時會較長。")

    # ================================================================
    # Tab 4: 進階檢索與切塊調校
    # ================================================================
    with tab_advanced:
        st.markdown("### 🎯 兩階段檢索微調")
        use_reranker = st.toggle("啟用 Cross-Encoder 深度重排序", value=settings.get("use_reranker", True))
        reranker_model = st.selectbox(
            "Reranker 模型名稱",
            options=["BAAI/bge-reranker-v2-m3", "BAAI/bge-reranker-large", "BAAI/bge-reranker-base"],
            index=0 if settings.get("reranker_model") == "BAAI/bge-reranker-v2-m3" else 2
        )

        k_col1, k_col2 = st.columns(2)
        with k_col1:
            initial_k = st.slider("初篩候選數量 (INITIAL_RETRIEVAL_K)", 5, 50, int(settings.get("initial_retrieval_k", 15)), 5)
        with k_col2:
            final_k = st.slider("精準送入 LLM 數量 (FINAL_TOP_K)", 1, 15, int(settings.get("final_top_k", 5)), 1)

        st.divider()
        st.markdown("### 🧠 生成與切塊設定")
        t_col1, t_col2 = st.columns(2)
        with t_col1:
            temperature = st.slider("模型生成溫度", 0.0, 1.0, float(settings.get("llm_temperature", 0.1)), 0.05)
        with t_col2:
            max_tokens = st.number_input("上下文視窗預算", 2048, 65536, int(settings.get("max_context_tokens", 16384)), 2048)

        c_col1, c_col2, c_col3 = st.columns(3)
        with c_col1:
            chunk_size = st.number_input("切塊大小", 150, 1000, int(settings.get("chunk_size", 400)), 50)
        with c_col2:
            chunk_overlap = st.number_input("重疊字數", 0, 200, int(settings.get("chunk_overlap", 60)), 10)
        with c_col3:
            enable_s2t = st.toggle("自動簡轉繁", value=bool(settings.get("enable_s2t", True)))

    # ================================================================
    # Tab 5: 系統硬體與 CUDA 診斷
    # ================================================================
    with tab_diag:
        st.markdown("### 🔍 系統環境與 GPU 加速診斷")
        d1, d2 = st.columns(2)
        d1.metric("Python 執行檔", os.path.basename(sys.executable))
        d2.metric("Python 版本", sys.version.split()[0])
        st.code(f"完整路徑: {sys.executable}\n工作目錄: {os.getcwd()}", language="bash")

        venv = os.environ.get("VIRTUAL_ENV")
        if venv:
            st.success(f"✅ 運行於虛擬環境: `{venv}`")
        else:
            st.warning("⚠️ 運行於系統全域環境")

        st.divider()
        try:
            import torch
            col_t1, col_t2 = st.columns(2)
            col_t1.metric("PyTorch 版本", torch.__version__)
            cuda_ok = torch.cuda.is_available()
            if cuda_ok:
                col_t2.metric("CUDA 加速支援", "✅ 可用 (True)")
                st.success(f"CUDA 版本: {getattr(torch.version, 'cuda', 'N/A')} | 偵測到 {torch.cuda.device_count()} 塊 GPU")
                for i in range(torch.cuda.device_count()):
                    st.info(f"🎮 GPU {i}: **{torch.cuda.get_device_name(i)}**")
            else:
                col_t2.metric("CUDA 加速支援", "❌ 不可用 (僅支援 CPU)")
                st.info("提示：如果系統沒有 NVIDIA 顯示卡，請至「🖥️ 計算裝置」切換為 CPU 模式即可正常運作。")
        except ImportError:
            st.error("❌ 系統未安裝 PyTorch！")

    # ================================================================
    # 底部全域儲存按鈕
    # ================================================================
    st.divider()
    if st.button("💾 儲存全部設定並重啟 AI 引擎", type="primary", use_container_width=True):
        new_settings = {
            "llm_provider": "cloud" if use_cloud else "local",
            "ollama_base_url": ollama_url.strip(),
            "ollama_model": ollama_model.strip(),
            "cloud_provider": cloud_provider,
            "cloud_api_key": cloud_api_key.strip(),
            "cloud_model": cloud_model.strip(),
            "cloud_base_url": cloud_base_url.strip(),
            "compute_device": target_device,
            "preset_profile": "🛠️ 自訂進階模式",
            "use_reranker": use_reranker,
            "reranker_model": reranker_model.strip(),
            "initial_retrieval_k": int(initial_k),
            "final_top_k": int(final_k),
            "llm_temperature": float(temperature),
            "max_context_tokens": int(max_tokens),
            "chunk_size": int(chunk_size),
            "chunk_overlap": int(chunk_overlap),
            "enable_s2t": bool(enable_s2t),
        }
        save_settings(new_settings)
        _apply_settings_to_config(new_settings, config)

        st.session_state.need_reinit = True
        st.session_state.settings_updated = True
        st.success(f"✅ 設定已儲存！計算裝置切換為【{target_device.upper()}】，AI 引擎已重新初始化。")
        st.rerun()