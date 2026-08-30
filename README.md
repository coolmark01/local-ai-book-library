# AI 私人圖書館

基於 RAG（檢索增強生成）的智能書籍問答系統。上傳任何書籍（PDF / EPUB / TXT），系統自動將其向量化存入知識庫，然後透過本地端大語言模型進行基於書籍內容的問答。

## 功能特色

- **智能問答**：基於書庫內容的 RAG 問答，支援深度思考模式 (CoT)
- **混合檢索**：向量相似度 + BM25 關鍵字雙路召回
- **詞雲可視化**：從全庫文件中提取高頻關鍵詞
- **每日書摘**：AI 從書庫中提煉讀書洞察
- **多格式支援**：PDF / EPUB / TXT
- **全本地化**：LLM 和嵌入模型均在本地運行，無需外部 API

## 技術架構

| 層級 | 技術 |
|------|------|
| 前端 UI | Streamlit |
| LLM | Ollama (Qwen 3.5:9B) |
| 文字嵌入 | BAAI/bge-small-zh-v1.5 |
| 向量資料庫 | ChromaDB |
| 檢索策略 | 向量 + BM25 混合檢索 |
| 文字處理 | LangChain TextSplitter + OpenCC |

## 專案結構

```
ai_book_library/
├── app.py                  # 主入口 + 側邊欄 + 頁面路由
├── config.py               # 配置中心（模型、路徑、參數）
├── text_processor.py       # 文字清洗、簡轉繁、停用詞
├── document_loader.py      # 文件解析 + 切塊 + 向量化
├── retrieval_engine.py     # 混合檢索 + QA Chain + 統計
├── visualization.py        # 詞雲 + 每日書摘
├── ui_qa.py                # 問答頁面 UI
├── ui_knowledge.py         # 知識圖譜頁面 UI
├── ui_manage.py            # 知識庫管理頁面 UI
├── requirements.txt        # 依賴清單
└── README.md               # 本文件
```

## 快速開始

### 1. 安裝依賴

```bash
pip install -r requirements.txt
```

### 2. 安裝 Ollama 並拉取模型

```bash
# 安裝 Ollama (https://ollama.com)
curl -fsSL https://ollama.com/install.sh | sh

# 拉取模型
ollama pull qwen3.5:9b
```

### 3. 啟動應用

```bash
streamlit run app.py
```

## 模組說明與優化指南

每個模組檔案都是**獨立可替換**的。當你想優化某個功能時：

| 想優化什麼 | 替換哪個檔案 |
|-----------|-------------|
| 換 LLM 模型或調整參數 | `config.py` |
| 改文字清洗規則或停用詞 | `text_processor.py` |
| 改切塊策略或新增檔案格式 | `document_loader.py` |
| 改檢索策略、Prompt 或生成邏輯 | `retrieval_engine.py` |
| 改詞雲樣式或書摘生成 | `visualization.py` |
| 改問答 UI | `ui_qa.py` |
| 改知識圖譜 UI | `ui_knowledge.py` |
| 改上傳管理 UI | `ui_manage.py` |
| 改導航或整體佈局 | `app.py` |

### 替換流程

1. 告訴 AI 你想優化哪個模組
2. AI 只需生成該模組的新版程式碼
3. 你直接替換對應檔案即可
4. 重新啟動 `streamlit run app.py`

## 配置說明

所有可調參數集中在 `config.py` 中，包括：

- `MODEL_NAME`：Ollama 模型名稱
- `EMBEDDING_MODEL_NAME`：嵌入模型
- `CHUNK_SIZE` / `CHUNK_OVERLAP`：文字切塊大小
- `TOP_K`：檢索返回的片段數量
- `ENABLE_S2T`：是否啟用簡體轉繁體
- `MAX_CONTEXT_TOKENS`：LLM 上下文窗口大小

## 授權

MIT License
