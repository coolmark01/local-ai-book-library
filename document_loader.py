# -*- coding: utf-8 -*-
"""
文件載入模組 (document_loader.py)
==================================
負責：多格式文件解析 (PDF/EPUB/TXT)、OCR 降級調度、切塊與向量庫寫入。
具備非標準 EPUB 的 ZIP 底層容錯解析機制，杜絕 ElementTree XML 崩潰問題。
"""

import os
import gc
import zipfile
import logging
import concurrent.futures
from typing import List, Dict, Any, Optional, Callable

import ebooklib
from ebooklib import epub
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

# 現代化 LangChain 0.2+ 引用，兼顧舊版相容
try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:
    from langchain_community.embeddings import HuggingFaceEmbeddings

try:
    from langchain_chroma import Chroma
except ImportError:
    from langchain_community.vectorstores import Chroma

from config import RAGConfig
from text_processor import clean_html_content, clean_pdf_text, convert_to_traditional
from pdf_text_extractor import extract_pdf_text_with_quality

logger = logging.getLogger("LibraryLogger")
EPUB_READ_TIMEOUT = 120

# 全域快取池，使用配置特徵作為快取鍵
_EMBEDDINGS_POOL: Dict[str, Any] = {}


def get_embeddings_model(config: RAGConfig) -> Any:
    """
    獲取 HuggingFaceEmbeddings 實例。
    支援依據模型名、裝置類型動態切換快取，並具備 CUDA 故障自動降級機制。
    """
    cache_key = f"{config.EMBEDDING_MODEL_NAME}_{config.EMBEDDING_DEVICE}_{config.EMBEDDING_BATCH_SIZE}"
    if cache_key in _EMBEDDINGS_POOL:
        return _EMBEDDINGS_POOL[cache_key]

    target_device = config.EMBEDDING_DEVICE
    try:
        embeddings = HuggingFaceEmbeddings(
            model_name=config.EMBEDDING_MODEL_NAME,
            model_kwargs={"device": target_device},
            encode_kwargs={
                "normalize_embeddings": True,
                "batch_size": config.EMBEDDING_BATCH_SIZE,
            },
        )
        logger.info(f"[Loader] 嵌入模型載入成功 (Model: {config.EMBEDDING_MODEL_NAME}, Device: {target_device})")
        _EMBEDDINGS_POOL[cache_key] = embeddings
        return embeddings
    except Exception as e:
        logger.error(f"[Loader] 嵌入模型在 {target_device} 上載入失敗: {e}，嘗試降級至 CPU 模式")
        cpu_key = f"{config.EMBEDDING_MODEL_NAME}_cpu_{config.EMBEDDING_BATCH_SIZE}"
        if cpu_key in _EMBEDDINGS_POOL:
            return _EMBEDDINGS_POOL[cpu_key]

        embeddings = HuggingFaceEmbeddings(
            model_name=config.EMBEDDING_MODEL_NAME,
            model_kwargs={"device": "cpu"},
            encode_kwargs={
                "normalize_embeddings": True,
                "batch_size": config.EMBEDDING_BATCH_SIZE,
            },
        )
        logger.info(f"[Loader] 嵌入模型已成功降級至 CPU 模式")
        _EMBEDDINGS_POOL[cpu_key] = embeddings
        return embeddings


def get_vectorstore(config: RAGConfig) -> Chroma:
    """取得 Chroma 向量資料庫實例（遵循最新自動持久化標準）。"""
    embeddings = get_embeddings_model(config)
    try:
        return Chroma(
            persist_directory=config.CHROMA_PERSIST_DIR,
            embedding_function=embeddings,
        )
    except Exception as e:
        logger.error(f"[Loader] 向量資料庫初始化失敗: {e}", exc_info=True)
        raise RuntimeError(f"向量資料庫載入失敗: {e}") from e


def _parse_epub_fallback_zip(file_path: str) -> List[Dict[str, Any]]:
    """
    底層 ZIP 直接容錯解析：
    當非標準 EPUB 造成 ebooklib (XML/lxml) 解析崩潰時，直接讀取 ZIP 內的 HTML/XHTML 章節。
    """
    documents = []
    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            namelist = zf.namelist()
            # 篩選所有內容頁面
            html_files = [
                name for name in namelist
                if name.lower().endswith((".html", ".xhtml", ".htm"))
                and not name.startswith("__MACOSX")
            ]
            html_files.sort()

            for filename in html_files:
                try:
                    raw_bytes = zf.read(filename)
                    html_text = ""
                    for enc in ("utf-8", "gb18030", "gbk", "big5", "latin-1"):
                        try:
                            html_text = raw_bytes.decode(enc)
                            break
                        except UnicodeDecodeError:
                            continue

                    if not html_text:
                        html_text = raw_bytes.decode("utf-8", errors="ignore")

                    cleaned = clean_html_content(html_text)
                    if cleaned and len(cleaned.strip()) > 30:
                        chapter_title = os.path.splitext(os.path.basename(filename))[0]
                        documents.append({
                            "page_content": cleaned,
                            "metadata": {
                                "source_type": "epub",
                                "chapter": chapter_title,
                            }
                        })
                except Exception as file_err:
                    logger.warning(f"[Loader] ZIP 提取章節失敗 ({filename}): {file_err}")
    except Exception as e:
        logger.error(f"[Loader] ZIP 原生容錯解析失敗: {e}", exc_info=True)

    return documents


def _parse_epub_with_timeout(file_path: str, timeout: int = EPUB_READ_TIMEOUT) -> List[Dict[str, Any]]:
    """使用執行緒池與雙軌機制解析 EPUB 檔案（ebooklib 標準模式 + ZIP 原生容錯模式）。"""
    def _read():
        documents = []
        try:
            # 優先使用 ebooklib 標準解析
            book = epub.read_epub(file_path)
            for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
                content_bytes = item.get_content()
                html_content = content_bytes.decode("utf-8", errors="ignore")
                cleaned_text = clean_html_content(html_content)
                if cleaned_text and len(cleaned_text) > 30:
                    chapter_name = item.get_name() or "未知章節"
                    documents.append({
                        "page_content": cleaned_text,
                        "metadata": {"source_type": "epub", "chapter": chapter_name},
                    })
        except Exception as e:
            logger.warning(f"[Loader] ebooklib 標準解析失敗 ({e})，自動切換至 ZIP 容錯解析機制...")
            documents = _parse_epub_fallback_zip(file_path)

        # 若標準解析結果為空，亦嘗試後援解析
        if not documents:
            documents = _parse_epub_fallback_zip(file_path)

        return documents

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_read)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(f"EPUB 解析超時 ({timeout} 秒)，檔案可能過大或損壞。")


def process_and_store_document(
    file_path: str,
    filename: str,
    config: RAGConfig,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> int:
    """
    文件處理主管線：解析 -> 清洗 -> 簡轉繁 -> 切塊 -> 向量化寫入。
    回傳：新增的知識片段 (Chunk) 數量。
    """
    raw_texts: List[Dict[str, Any]] = []

    # 階段 1/5：解析檔案
    if progress_callback:
        progress_callback(0, 5, f"正在解析 {filename}...")
    logger.info(f"[Loader] 階段 1/5：開始解析 {filename}")

    try:
        ext = os.path.splitext(filename)[1].lower()

        if ext == ".pdf":
            pdf_text, quality = extract_pdf_text_with_quality(file_path)
            if pdf_text and len(pdf_text.strip()) > 0:
                cleaned = clean_pdf_text(pdf_text)
                if cleaned:
                    raw_texts.append({
                        "content": cleaned,
                        "meta": {
                            "source": filename,
                            "filename": filename,
                            "type": "pdf",
                            "file_type": "pdf",
                            "ocr_quality": quality.get("score", 0),
                            "ocr_level": quality.get("level", "unknown"),
                        },
                    })
                    logger.info(f"[Loader] PDF 解析完成 | 品質評分: {quality.get('score', 0)} ({quality.get('level')})")
            else:
                logger.error(f"[Loader] PDF 無法提取文字: {filename}")
                if progress_callback:
                    progress_callback(5, 5, f"PDF 無法提取文字: {filename}")
                return 0

        elif ext == ".epub":
            docs = _parse_epub_with_timeout(file_path)
            for doc in docs:
                if doc["page_content"]:
                    raw_texts.append({
                        "content": doc["page_content"],
                        "meta": {
                            "source": filename,
                            "filename": filename,
                            "type": "epub",
                            "file_type": "epub",
                            "chapter": doc["metadata"].get("chapter", ""),
                            "ocr_quality": 100,
                            "ocr_level": "good",
                        },
                    })
            logger.info(f"[Loader] EPUB 解析完成，共 {len(raw_texts)} 個段落")

        elif ext == ".txt":
            loader = TextLoader(file_path, encoding="utf-8")
            docs = loader.load()
            for doc in docs:
                raw_texts.append({
                    "content": doc.page_content,
                    "meta": {
                        "source": filename,
                        "filename": filename,
                        "type": "txt",
                        "file_type": "txt",
                        "ocr_quality": 100,
                        "ocr_level": "good",
                    },
                })
            logger.info(f"[Loader] TXT 解析完成")
        else:
            logger.warning(f"[Loader] 不支援的副檔名: {filename}")
            return 0

    except Exception as e:
        logger.error(f"[Loader] 檔案解析異常 ({filename}): {e}", exc_info=True)
        if progress_callback:
            progress_callback(5, 5, f"解析失敗: {e}")
        raise RuntimeError(f"檔案解析失敗: {e}") from e

    if not raw_texts:
        if progress_callback:
            progress_callback(5, 5, "解析後未取得有效文字")
        return 0

    # 階段 2/5：文字清洗與簡繁轉換
    if progress_callback:
        progress_callback(1, 5, "正在清洗文字與轉換簡繁...")
    logger.info("[Loader] 階段 2/5：文字清洗與轉換")

    processed_texts = []
    for item in raw_texts:
        converted_content = convert_to_traditional(item["content"], enable=config.ENABLE_S2T)
        processed_texts.append({
            "content": converted_content,
            "meta": item["meta"]
        })

    # 階段 3/5：切塊處理
    if progress_callback:
        progress_callback(2, 5, "正在切分知識片段...")
    logger.info(f"[Loader] 階段 3/5：切塊處理 (Chunk Size: {config.CHUNK_SIZE}, Overlap: {config.CHUNK_OVERLAP})")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
        separators=config.CHUNK_SEPARATORS,
    )

    final_chunks: List[Document] = []
    for item in processed_texts:
        doc = Document(page_content=item["content"], metadata=item["meta"])
        chunks = splitter.split_documents([doc])
        final_chunks.extend(chunks)

    if not final_chunks:
        logger.warning("[Loader] 切塊後未產生任何有效知識片段")
        if progress_callback:
            progress_callback(5, 5, "切塊後未產生有效片段")
        return 0

    logger.info(f"[Loader] 切塊完成，生成 {len(final_chunks)} 個知識片段")

    # 階段 4/5：向量化並寫入 ChromaDB
    if progress_callback:
        progress_callback(3, 5, f"正在向量化寫入 (0/{len(final_chunks)})...")
    logger.info("[Loader] 階段 4/5：批次向量化寫入")

    try:
        vectorstore = get_vectorstore(config)
        batch_size = config.EMBEDDING_BATCH_SIZE
        total = len(final_chunks)
        stored_count = 0

        for i in range(0, total, batch_size):
            batch = final_chunks[i : i + batch_size]
            vectorstore.add_documents(batch)
            stored_count += len(batch)
            if progress_callback:
                progress_callback(
                    3, 5,
                    f"正在向量化寫入 ({min(stored_count, total)}/{total})..."
                )

        logger.info(f"[Loader] 向量化寫入完成，成功存入 {stored_count} 筆片段")

    except Exception as e:
        logger.error(f"[Loader] 向量化寫入失敗: {e}", exc_info=True)
        if progress_callback:
            progress_callback(5, 5, f"向量化寫入失敗: {e}")
        raise RuntimeError(f"向量化失敗: {e}") from e

    # 階段 5/5：完成與資源釋放
    if progress_callback:
        progress_callback(5, 5, "處理完成！")

    gc.collect()
    logger.info(f"[Loader] 全部流程完成: {filename} -> {len(final_chunks)} chunks")
    return len(final_chunks)