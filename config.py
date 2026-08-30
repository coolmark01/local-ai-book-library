# -*- coding: utf-8 -*-
"""
配置中心 (config.py)
====================
集中管理所有可調參數：路徑、嵌入模型、Reranker 模型、計算裝置 (CPU/CUDA)、
LLM 參數、檢索策略與資料庫設定。
"""

import os
from typing import List


class RAGConfig:
    """RAG 系統全域配置類別"""

    # --- 路徑設定（絕對路徑） ---
    _BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))
    UPLOAD_DIR: str = os.path.join(_BASE_DIR, "uploaded_books")
    CHROMA_PERSIST_DIR: str = os.path.join(_BASE_DIR, "chroma_db")

    # --- 計算裝置全域設定 (支援 "cuda" 或 "cpu") ---
    # 可在系統設定頁動態切換，供非 NVIDIA 顯示卡或純 CPU 設備使用
    EMBEDDING_DEVICE: str = "cuda"
    RERANKER_DEVICE: str = "cuda"

    # --- 嵌入模型 (Dense Vector) ---
    EMBEDDING_MODEL_NAME: str = "BAAI/bge-small-zh-v1.5"
    EMBEDDING_BATCH_SIZE: int = 128

    # --- 重排序模型 (Cross-Encoder Reranker) ---
    USE_RERANKER: bool = True
    RERANKER_MODEL_NAME: str = "BAAI/bge-reranker-v2-m3"
    INITIAL_RETRIEVAL_K: int = 15  # 第一階段初篩候選池大小（向量 + BM25 各自取樣數）
    FINAL_TOP_K: int = 5          # 第二階段經 Reranker 重排後最終保留的精華片段數

    # --- LLM 設定 ---
    LLM_PROVIDER: str = "local"  # "local" 或 "cloud"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    MODEL_NAME: str = "qwen3.5:9b"
    LLM_TEMPERATURE: float = 0.1
    LLM_NUM_PREDICT: int = 8192

    # --- Token 與上下文預算 ---
    MAX_CONTEXT_TOKENS: int = 16384
    RESERVED_TOKENS: int = 800

    # --- 檢索參數（向後相容） ---
    TOP_K: int = 5
    BM25_K: int = 15

    # --- 文字切塊設定 (配合 512 token 上限) ---
    CHUNK_SIZE: int = 400
    CHUNK_OVERLAP: int = 60
    CHUNK_SEPARATORS: List[str] = None

    # --- 資料庫批次操作設定 ---
    DB_BATCH_SIZE: int = 500

    # --- 簡繁轉換開關 ---
    ENABLE_S2T: bool = True

    # --- 視覺化與詞雲設定 ---
    WORD_CLOUD_MAX_WORDS: int = 100
    WORD_CLOUD_WIDTH: int = 800
    WORD_CLOUD_HEIGHT: int = 400
    WORD_CLOUD_TOP_N: int = 100

    # --- 每日書摘設定 ---
    INSIGHT_SEARCH_QUERIES: List[str] = None
    INSIGHT_MAX_RETRIES: int = 2
    INSIGHT_CONTEXT_MAX_CHARS: int = 350
    INSIGHT_MIN_LENGTH: int = 10

    def __post_init__(self):
        if self.CHUNK_SEPARATORS is None:
            self.CHUNK_SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", "…", ".", " "]
        if self.INSIGHT_SEARCH_QUERIES is None:
            self.INSIGHT_SEARCH_QUERIES = [
                "核心觀點", "重要結論", "經典論述", "關鍵理論",
                "實踐方法", "思維模型", "人生哲理", "創新思維",
                "系統思考", "深度分析"
            ]

    @property
    def MAX_CONTEXT_CHUNK_TOKENS(self) -> int:
        return max(self.MAX_CONTEXT_TOKENS - self.RESERVED_TOKENS, 1000)

    def __init__(self):
        self.__post_init__()
        os.makedirs(self.UPLOAD_DIR, exist_ok=True)
        os.makedirs(self.CHROMA_PERSIST_DIR, exist_ok=True)