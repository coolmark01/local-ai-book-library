# 📚 Local AI Book Library & Second Brain (local-ai-book-library)

<p align="center">
  <a href="#-繁體中文">繁體中文</a> •
  <a href="#-english">English</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%20%7C%203.11-3776AB?logo=python&logoColor=white" alt="Python Version" />
  <img src="https://img.shields.io/badge/UI-Streamlit-FF4B4B?logo=streamlit&logoColor=white" alt="Streamlit UI" />
  <img src="https://img.shields.io/badge/Orchestration-LangChain-1C3C3C?logo=langchain&logoColor=white" alt="LangChain" />
  <img src="https://img.shields.io/badge/VectorDB-Chroma-orange" alt="ChromaDB" />
  <img src="https://img.shields.io/badge/Reranker-Cross--Encoder-purple" alt="Cross-Encoder" />
  <img src="https://img.shields.io/badge/PKM-Obsidian-7C3AED?logo=obsidian&logoColor=white" alt="Obsidian" />
  <img src="https://img.shields.io/badge/Vault-Second%20Brain-blueviolet" alt="Second Brain" />
  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License" />
</p>

---

## 🇹🇼 繁體中文

基於 **兩階段混合檢索（Two-Stage RAG）** 與 **Obsidian 數位第二大腦** 的本地隱私智慧書籍知識庫系統。

支援本機目錄遞迴掃描、書籍去重管理、多格式解析（PDF 智慧 OCR、EPUB、TXT）與向量化存入。透過本地大語言模型（Ollama / Cloud API）、Cross-Encoder 重排序模型、POS 詞性過濾思維圖譜與第二大腦筆記庫（Vault），提供深度問答、全庫主題綜整、每日靈感書摘、Obsidian 雙向連結筆記生成與知識庫持久化管理。

### 🌟 核心功能特色

- **🎯 兩階段混合檢索 (Two-Stage RAG)**：結合稠密語意向量（`bge-small-zh-v1.5` / `bge-m3`）與 BM25 關鍵字初篩，再經由 `BAAI/bge-reranker-v2-m3` 交叉注意力打分，徹底過濾檢索雜訊。
- **🧠 第二大腦筆記庫 (Second Brain Vault)**：全域輸出（問答洞察、專題申論、今日靈感）皆可一鍵存入本地 Vault (`vault_notes/`)，自動注入標準 YAML Frontmatter 元數據、`[[雙向連結]]` 與標籤，支援 Master-Detail 雙欄瀏覽、全文檢索與一鍵打包 ZIP 匯出。
- **📁 本機書籍目錄掃描與雙向同步 (Catalog Manager)**：支援 Windows 原生 GUI 目錄選取對話框與遞迴子資料夾掃描，具備絕對路徑防重複去重機制；與 ChromaDB 向量資料庫即時雙向同步入庫狀態（刪除自動恢復為未匯入），支援按需批次匯入。
- **📝 Obsidian PKM 2.0 筆記工作室**：提供 4 大筆記架構（單書精讀、多書交叉綜整、原子概念卡片、批判思維檢視），具備四層容錯檢索保底機制與靈感膠囊快速帶入主題。
- **💬 智慧書籍問答 & 操作列 (Inline Action Bar)**：支援思維鏈推演 (CoT)，每則回答下方內建微型操作列（一鍵複製、深度專題綜整、一鍵存入第二大腦與下載 .md）。
- **🕸️ 主題思維圖譜 (Theme-Driven Graph)**：採用 `jieba.posseg` 詞性標註過濾虛詞，支援領域思維導向（商業投資、心智模型、自訂關鍵字），具備本地快取、防卡頓確認按鈕與 **Obsidian 原生白板 (`.canvas`) 格式匯出**。
- **💡 今日靈感書摘 (Daily Insights)**：每日自動從書庫隨機提煉高濃度思想卡片與底層心智模型，支援日期快取與一鍵轉入筆記庫。
- **📚 雙視圖書庫管理**：支援「🗂️ 卡片網格」與「📋 緊湊清單」切換，內建 PDF OCR 辨識品質評分燈號（0–100 分）與片段分頁虛擬瀏覽器。
- **🖥️ 全本地隱私與硬體動態適配**：模型與向量資料庫完全在本地運行；支援一鍵切換 **CUDA GPU 加速** 與 **CPU 通用相容模式**。

### 🏗️ 技術架構

| 層級 | 技術方案 | 說明 |
| :--- | :--- | :--- |
| **前端介面 (UI)** | Streamlit | 模組化多頁面、動態圖譜與操作響應 |
| **第二大腦管理 (PKM)** | VaultManager + Obsidian Syntax | YAML Frontmatter、`[[Wikilinks]]`、Callout 區塊與本地 Vault 同步 |
| **大語言模型 (LLM)** | Ollama / Cloud API | 預設支援 `qwen3.5:9b`、`llama3.1`、`deepseek` 或雲端 API |
| **文字嵌入 (Embedding)** | BAAI/bge-small-zh-v1.5 / bge-m3 | 支援中文專用或多語言稠密語意表徵 |
| **重排序 (Reranker)** | BAAI/bge-reranker-v2-m3 | Cross-Encoder 交叉注意力語意深度評分 |
| **向量資料庫** | ChromaDB | 本地持久化向量儲存 |
| **稀疏關鍵字索引** | Rank-BM25 + Jieba | 繁簡對齊精確文字檢索 |
| **圖譜與白板引擎** | Vis.js + Obsidian Canvas JSON | 力導向關係網絡與白板視覺化 |
| **文件解析與 OCR** | PyMuPDF (fitz) + Tesseract + EbookLib | 支援數位/掃描 PDF、EPUB (ZIP 容錯) 與 TXT |

### 📂 專案檔案結構

```text
local-ai-book-library/
├── app.py                   # 主入口 + 側邊欄狀態 + 頁面路由分發
├── config.py                # 配置中心（模型、路徑、檢索參數、Token 限制）
├── catalog_manager.py       # 本機目錄遞迴掃描、書籍去重與向量庫狀態雙向同步
├── vault_manager.py         # 第二大腦筆記庫管理器 (YAML 元數據、索引、搜尋、刪除、ZIP 打包)
├── document_loader.py       # 文件解析 + 自動 OCR 評分 + 安全切塊 + 向量化
├── text_processor.py        # 文字清洗、OpenCC 繁簡轉換與長度截斷
├── retrieval_engine.py      # 兩階段混合檢索 + QA Chain + 統計與全庫盤點
├── synthesis_engine.py      # 跨章節 / 多書籍深度專題綜整分析引擎
├── visualization.py         # POS 詞性過濾圖譜、快取管理、Canvas 轉換與今日書摘
├── obsidian_engine.py       # 4 種模式 Obsidian Markdown 生成引擎 ([[Wikilinks]])
├── obsidian_helper.py       # 跨模組共用操作列（存入第二大腦、一鍵複製、下載 .md）
├── ui_qa.py                 # 智慧對話問答介面 (含微型操作列與來源卡片)
├── ui_visualization.py      # 知識圖譜工作台 (含執行控制、終止按鈕與書摘分頁)
├── ui_obsidian.py           # Obsidian 專題筆記工作室 (含靈感膠囊與四層容錯檢索)
├── ui_vault.py              # 第二大腦筆記庫介面 (Master-Detail 雙欄瀏覽與全文檢索)
├── ui_manage.py             # 書庫管理頁面 (GUI 目錄選取、卡片/清單雙視圖、片段瀏覽)
├── ui_settings.py           # 系統設定 (模型設定、情境預設檔、CPU/CUDA 切換)
├── requirements.txt         # 專案套件依賴清單
└── README.md                # 專案說明文件
```

### 🚀 快速開始

#### 1. 安裝環境與依賴
```bash
python -m venv venv
.\venv\Scripts\Activate.ps1  # Windows PowerShell
# source venv/bin/activate   # Linux / macOS

pip install --upgrade pip
pip install -r requirements.txt
```

#### 2. 安裝 Ollama 並拉取模型
```bash
ollama pull qwen3.5:9b
# 或英文推薦模型：ollama pull llama3.1:8b
```

#### 3. 啟動應用
```bash
streamlit run app.py
```

### 🧩 模組說明與優化指南

每個模組檔案皆為**獨立可替換**設計。當你想優化特定功能時：

| 想優化什麼 | 替換哪個檔案 | 說明 |
| :--- | :--- | :--- |
| **調整模型、路徑或核心參數** | `config.py` | 調整預設 Top-K、Token 上限、模型名稱與路徑 |
| **調整本機目錄掃描或去重邏輯** | `catalog_manager.py` | 調整目錄遍歷深度、支援副檔名或狀態同步邏輯 |
| **優化第二大腦筆記儲存與元數據** | `vault_manager.py` | 調整 YAML Frontmatter 格式、標籤聚合或 ZIP 匯出 |
| **優化文字清洗或繁簡對齊** | `text_processor.py` | 調整 OpenCC 規則、標點與停用詞 |
| **升級書籍解析、OCR 或切塊** | `document_loader.py` | 增強 PDF OCR 辨識率、EPUB 解析或段落分割策略 |
| **升級檢索管線或 Prompt** | `retrieval_engine.py` | 調整兩階段 Hybrid Search、BM25 權重或問答提示詞 |
| **優化跨書深度綜整** | `synthesis_engine.py` | 調整專題研究綜整報告的推論邏輯與結構 |
| **優化思維圖譜、快取或書摘** | `visualization.py` | 調整 POS 詞性過濾、物理圖譜演算法或每日靈感 Prompt |
| **優化 Obsidian 筆記語法** | `obsidian_engine.py` | 調整 4 大筆記架構、雙向連結格式或 Callout 樣式 |
| **調整操作列按鈕或剪貼簿** | `obsidian_helper.py` | 調整「存入第二大腦」、「複製」或「下載」按鈕邏輯 |
| **調整問答互動或操作列** | `ui_qa.py` | 增修對話氣泡、微型操作列功能 |
| **調整圖譜介面與白板匯出** | `ui_visualization.py` | 調整圖譜參數控制表單、進度條或書摘卡片展示 |
| **調整 Obsidian 專題頁面** | `ui_obsidian.py` | 增減靈感膠囊主題、容錯檢索策略或筆記模式選擇介面 |
| **調整第二大腦筆記庫介面** | `ui_vault.py` | 調整 Master-Detail 佈局、標籤篩選或預覽模式 |
| **調整書庫管理與片段瀏覽** | `ui_manage.py` | 調整 GUI 資料夾選取、卡片/清單視圖排版或 OCR 徽章 |
| **調整硬體切換或系統設定** | `ui_settings.py` | 增修一鍵情境預設檔（快速/平衡/深度）或 CUDA 診斷 |
| **調整全域導航或側邊欄** | `app.py` | 調整頁面路由、日誌配置與引擎初始化生命週期 |

### ⚙️ 核心配置參數說明

所有全域參數集中於 `config.py`，亦可在前端「⚙️ 系統設定」動態調整：

| 參數名稱 | 預設值 | 說明 |
| :--- | :--- | :--- |
| `MODEL_NAME` | `qwen3.5:9b` | 主要語言模型名稱 (Ollama 或雲端 API) |
| `EMBEDDING_MODEL_NAME` | `BAAI/bge-small-zh-v1.5` | 向量嵌入模型（英文書庫建議改用 `BAAI/bge-m3`） |
| `RERANKER_MODEL_NAME` | `BAAI/bge-reranker-v2-m3` | Cross-Encoder 深度重排序模型 |
| `INITIAL_RETRIEVAL_K` | `15` | 第一階段混合檢索初篩候選片段數量 |
| `FINAL_TOP_K` | `5` | 第二階段經 Reranker 評分後送入 Prompt 的精華片段數 |
| `EMBEDDING_DEVICE` | `cuda` | 運算硬體裝置（`cuda` 啟用 GPU 加速，`cpu` 為相容模式） |
| `CHUNK_SIZE` | `400` | 文件切塊字元大小 |
| `CHUNK_OVERLAP` | `50` | 區塊間重疊字元數（保持語意連續性） |
| `ENABLE_S2T` | `True` | 自動將簡體中文轉為繁體中文以統一索引 |

---

## 🌐 English

An enterprise-grade, privacy-first **Local Personal Knowledge Management (PKM) OS** and **Two-Stage RAG Assistant** designed for personal digital libraries, deep research, and Obsidian workflows.

### 🌟 Key Highlights
* **🎯 Two-Stage Hybrid Search**: Dense Vector + BM25 Lexical Recall -> `BAAI/bge-reranker-v2-m3` Cross-Encoder scoring.
* **🧠 Built-in Second Brain Vault**: Instant archiving of QA insights, deep syntheses, and daily wisdom into a dedicated markdown vault (`vault_notes/`) with YAML frontmatter and `[[Wikilinks]]`.
* **📁 Local Directory Scanner & Catalog Manager**: Native GUI directory selection, recursive subfolder traversal, path de-duplication, and live bi-directional sync with ChromaDB.
* **📝 Obsidian PKM 2.0 Studio**: 4 note archetypes (*Deep Dive*, *Cross-Book Synthesis*, *Atomic Cards*, *Critical Review*) with multi-level fallback retrieval.
* **💬 Conversational QA with Action Bar**: Chain-of-Thought reasoning (CoT), inline copy, deep topic synthesis, and one-click vault archiving.
* **🕸️ Theme-Driven Knowledge Graph**: POS-filtered concept networks with domain lenses, persistent caching, and native **Obsidian Canvas (`.canvas`) whiteboard export**.
* **💡 Daily Insights Generator**: Date-cached daily golden quote cards with underlying mental model breakdowns.
* **📚 Dual-View Library Manager**: Card Grid & Compact List views, PDF OCR quality indicators (0–100), and paginated chunk reader.
* **🖥️ Hardware Agnostic**: On-the-fly toggling between **CUDA GPU Acceleration** and **CPU Mode**.

### ⚙️ English & Multilingual Adaptation
To optimize for an English book collection, configure `config.py`:
```python
# 1. Switch to a Multilingual/English Specialist Embedding Model
EMBEDDING_MODEL_NAME: str = "BAAI/bge-m3"  # or "BAAI/bge-small-en-v1.5"

# 2. Select an English LLM (in Settings or config.py)
MODEL_NAME: str = "llama3.1:8b"
```
In **🕸️ Knowledge Graph**, select **`🔍 Custom Focus Keywords`** and input your domain anchors (e.g., `Economy, Value Investing, Cash Flow, Moat, Margin of Safety, Asset Allocation`).

---

## 📄 授權 (License)

This project is licensed under the [MIT License](LICENSE).