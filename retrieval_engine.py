# -*- coding: utf-8 -*-
"""
檢索引擎模組 (retrieval_engine.py)
===================================
負責：
  1. 查詢端簡繁自動對齊 (修復 BM25 簡繁失配)
  2. 書名與 Metadata 優先召回增強
  3. 書庫全目錄感知 (支援「有哪些書籍是小說」等全庫盤點查詢)
  4. 兩階段混合檢索 (向量 + BM25 擴大召回 -> Cross-Encoder 精準重排序)
  5. 書庫資料管理與深度綜整調度
"""

import os
import re
import time
import logging
from typing import List, Dict, Any, Optional, Tuple

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

try:
    from langchain_community.retrievers import BM25Retriever
    HAS_BM25 = True
except ImportError:
    HAS_BM25 = False

try:
    from sentence_transformers import CrossEncoder
    HAS_CROSS_ENCODER = True
except ImportError:
    HAS_CROSS_ENCODER = False

from config import RAGConfig
from document_loader import get_vectorstore
from visualization import VisualizationEngine
from synthesis_engine import SynthesisEngine
from text_processor import convert_to_traditional

logger = logging.getLogger("LibraryLogger")


class BookRAGEngine:
    """通用書籍 RAG 引擎，支援目錄感知、Metadata 增強與兩階段混合檢索。"""

    def __init__(self, config: Optional[RAGConfig] = None):
        self.config = config or RAGConfig()
        self.vectorstore = None
        self.bm25_retriever: Optional[BM25Retriever] = None
        self.reranker: Optional[Any] = None
        self.llm = None
        self.viz_engine: Optional[VisualizationEngine] = None
        self.synthesizer: Optional[SynthesisEngine] = None
        self.is_ready: bool = False
        self._init_components()

    # ------------------------------------------------------------------ 初始化
    def _init_components(self):
        try:
            self.vectorstore = get_vectorstore(self.config)
            logger.info("[Engine] 向量資料庫載入成功")
        except Exception as e:
            logger.error(f"[Engine] 向量資料庫載入失敗: {e}", exc_info=True)
            self.vectorstore = None

        self.bm25_retriever = self._init_bm25()
        self.reranker = self._init_reranker()
        self.llm = self._init_llm()
        self.viz_engine = VisualizationEngine(self.vectorstore)

        if self.llm is not None:
            self.synthesizer = SynthesisEngine(llm=self.llm)
            logger.info("[Engine] 深度綜整引擎初始化完成")
        else:
            self.synthesizer = None

        self.is_ready = bool(self.vectorstore is not None and self.llm is not None)
        logger.info(f"[Engine] 系統就緒狀態: {'✅ 正常' if self.is_ready else '❌ 未就緒'}")

    def _init_bm25(self) -> Optional[BM25Retriever]:
        if not HAS_BM25 or not self.vectorstore:
            return None
        try:
            collection = self.vectorstore._collection
            results = collection.get(include=["documents", "metadatas"])
            docs_text = results.get("documents", [])
            metadatas = results.get("metadatas", [])

            if not docs_text:
                return None

            all_docs = []
            for text, meta in zip(docs_text, metadatas):
                if text and text.strip():
                    all_docs.append(Document(page_content=text, metadata=meta or {}))

            if not all_docs:
                return None

            bm25 = BM25Retriever.from_documents(all_docs)
            bm25.k = self.config.INITIAL_RETRIEVAL_K
            logger.info(f"[Engine] BM25 初始化成功，已索引全庫 {len(all_docs)} 筆片段")
            return bm25
        except Exception as e:
            logger.error(f"[Engine] BM25 初始化失敗: {e}", exc_info=True)
            return None

    def _init_reranker(self) -> Optional[Any]:
        if not self.config.USE_RERANKER or not HAS_CROSS_ENCODER:
            return None
        model_name = self.config.RERANKER_MODEL_NAME
        target_device = self.config.RERANKER_DEVICE
        try:
            reranker = CrossEncoder(model_name, device=target_device, trust_remote_code=True)
            logger.info(f"[Engine] ✅ Reranker 載入成功 ({target_device.upper()})")
            return reranker
        except Exception as e:
            logger.warning(f"[Engine] Reranker 切換至 CPU: {e}")
            try:
                return CrossEncoder(model_name, device="cpu", trust_remote_code=True)
            except Exception as e2:
                logger.error(f"[Engine] Reranker 初始化失敗: {e2}")
                return None

    def rebuild_bm25(self):
        self.bm25_retriever = self._init_bm25()

    def _init_llm(self):
        try:
            from ui_settings import load_settings
            user_settings = load_settings()
        except Exception:
            user_settings = {}

        provider = user_settings.get("llm_provider", "local")

        if provider == "cloud":
            cloud_provider = user_settings.get("cloud_provider", "OpenAI")
            api_key = user_settings.get("cloud_api_key", "").strip()
            model_name = user_settings.get("cloud_model", "").strip()
            base_url = user_settings.get("cloud_base_url", "").strip()

            if api_key and model_name:
                try:
                    if cloud_provider == "OpenAI":
                        from langchain_openai import ChatOpenAI
                        return ChatOpenAI(model=model_name, api_key=api_key, temperature=self.config.LLM_TEMPERATURE)
                    elif cloud_provider == "Anthropic":
                        from langchain_anthropic import ChatAnthropic
                        return ChatAnthropic(model=model_name, api_key=api_key, temperature=self.config.LLM_TEMPERATURE)
                    elif cloud_provider == "Google Gemini":
                        from langchain_google_genai import ChatGoogleGenerativeAI
                        return ChatGoogleGenerativeAI(model=model_name, google_api_key=api_key, temperature=self.config.LLM_TEMPERATURE)
                    elif cloud_provider == "OpenAI 相容（自訂端點）":
                        from langchain_openai import ChatOpenAI
                        return ChatOpenAI(model=model_name, api_key=api_key, base_url=base_url if base_url else None, temperature=self.config.LLM_TEMPERATURE)
                except Exception as e:
                    logger.error(f"[Engine] 雲端 LLM 初始化失敗: {e}")

        try:
            from langchain_ollama import ChatOllama
            ollama_url = getattr(self.config, 'OLLAMA_BASE_URL', None) or user_settings.get("ollama_base_url", "http://localhost:11434")
            model = user_settings.get("ollama_model", "").strip() or self.config.MODEL_NAME

            llm_kwargs = {
                "model": model,
                "temperature": self.config.LLM_TEMPERATURE,
                "num_ctx": self.config.MAX_CONTEXT_TOKENS,
                "num_predict": self.config.LLM_NUM_PREDICT,
            }
            if ollama_url and ollama_url not in ("http://localhost:11434", "http://127.0.0.1:11434"):
                llm_kwargs["base_url"] = ollama_url

            return ChatOllama(**llm_kwargs)
        except Exception as e:
            logger.error(f"[Engine] Ollama 初始化失敗: {e}", exc_info=True)
            return None

    # ---------------------------------------------------------------- 兩階段檢索核心
    def _hybrid_search(self, query: str) -> Tuple[List[Document], List[str]]:
        """
        兩階段檢索：
        1. 簡繁對齊轉換 (處理簡繁失配)
        2. 書名/Metadata 優先匹配補充
        3. 向量 + BM25 候選池召回
        4. Cross-Encoder 精準重排序
        """
        log_lines = []
        start_time = time.time()

        # 1. 簡繁轉換對齊
        norm_query = convert_to_traditional(query, enable=self.config.ENABLE_S2T)
        if norm_query != query:
            log_lines.append(f"【查詢簡繁對齊】: '{query}' -> '{norm_query}'")

        candidates: List[Document] = []
        seen_keys = set()
        initial_k = self.config.INITIAL_RETRIEVAL_K

        # 2. Metadata / 書名精確命中補充（防止作者或書名在內文提及過少）
        meta_hit_count = 0
        if self.vectorstore:
            try:
                books = self.get_book_list_with_chunk_counts()
                for b in books:
                    b_name = b.get("filename", "")
                    # 如果使用者查詢包含書名關鍵字，或書名包含查詢關鍵字
                    if (len(norm_query) >= 2 and norm_query in b_name) or (len(b_name) >= 2 and b_name in norm_query):
                        matched_source = b.get("source")
                        chunks = self.get_book_chunks(matched_source)
                        # 挑選前 3 個片段作為 Metadata 補充候選
                        for chunk in chunks[:3]:
                            doc = Document(page_content=chunk["content"], metadata=chunk["metadata"])
                            key = doc.page_content[:120].strip()
                            if key not in seen_keys:
                                seen_keys.add(key)
                                candidates.append(doc)
                                meta_hit_count += 1
                if meta_hit_count > 0:
                    log_lines.append(f"【書名/Metadata 匹配】成功鎖定書名關聯，補充 {meta_hit_count} 筆候選")
            except Exception as e:
                logger.warning(f"[Retrieval] Metadata 匹配異常: {e}")

        # 3A. 向量稠密檢索（同時使用原詞與繁體詞搜尋）
        vector_count = 0
        if self.vectorstore:
            try:
                v_results = self.vectorstore.similarity_search(norm_query, k=initial_k)
                for doc in v_results:
                    key = doc.page_content[:120].strip()
                    if key not in seen_keys:
                        seen_keys.add(key)
                        candidates.append(doc)
                        vector_count += 1
            except Exception as e:
                logger.error(f"[Retrieval] 向量檢索初篩失敗: {e}")

        # 3B. BM25 稀疏檢索（使用繁體詞匹配）
        bm25_count = 0
        if self.bm25_retriever:
            try:
                bm25_docs = self.bm25_retriever.invoke(norm_query)
                for doc in bm25_docs:
                    key = doc.page_content[:120].strip()
                    if key not in seen_keys:
                        seen_keys.add(key)
                        candidates.append(doc)
                        bm25_count += 1
            except Exception as e:
                logger.error(f"[Retrieval] BM25 初篩失敗: {e}")

        stage1_time = time.time() - start_time
        log_lines.append(f"【階段 1 候選召回】向量 {vector_count} 筆 + BM25 {bm25_count} 筆 + 書名命中 {meta_hit_count} 筆，候選池共 {len(candidates)} 筆 (耗時: {stage1_time:.3f}s)")

        if not candidates:
            return [], log_lines

        # 4. Cross-Encoder 重排序
        final_top_k = self.config.FINAL_TOP_K

        if self.reranker and len(candidates) > 1:
            rerank_start = time.time()
            try:
                pairs = [[norm_query, doc.page_content] for doc in candidates]
                scores = self.reranker.predict(pairs)

                scored_docs = list(zip(candidates, scores))
                scored_docs.sort(key=lambda x: x[1], reverse=True)

                rerank_time = time.time() - rerank_start
                log_lines.append(f"【階段 2 交叉重排序】Reranker 完成評分 (耗時: {rerank_time:.3f}s)")

                final_docs = []
                for rank, (doc, score) in enumerate(scored_docs[:final_top_k], start=1):
                    doc.metadata["rerank_score"] = float(score)
                    final_docs.append(doc)
                    src_name = doc.metadata.get("filename") or doc.metadata.get("source", "未知")
                    preview = doc.page_content[:40].replace("\n", " ")
                    log_lines.append(f"  Top {rank} [Score: {score:.4f}] 《{src_name}》: {preview}...")

                return final_docs, log_lines

            except Exception as e:
                logger.error(f"[Retrieval] Reranker 執行異常: {e}", exc_info=True)
                log_lines.append(f"⚠️ Reranker 評分失敗 ({e})，降級採用初篩候選順序")
                return candidates[:final_top_k], log_lines
        else:
            log_lines.append(f"【階段 2】未啟用 Reranker，直接截取前 {final_top_k} 筆")
            return candidates[:final_top_k], log_lines

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        if not text:
            return 0
        cjk_chars = len(re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf\u3000-\u303f]', text))
        ascii_words = len(re.findall(r'\b[a-zA-Z0-9_-]+\b', text))
        other_chars = max(len(text) - cjk_chars - (ascii_words * 4), 0)
        return int(cjk_chars * 1.1 + ascii_words * 1.3 + other_chars * 1.0) + 5

    def _format_docs_with_token_limit(self, docs: List[Document]) -> str:
        if not docs:
            return "書庫中無相關參考文獻。"

        formatted_parts = []
        accumulated_tokens = 0
        max_tokens = self.config.MAX_CONTEXT_CHUNK_TOKENS

        for i, doc in enumerate(docs, start=1):
            source = doc.metadata.get("filename") or doc.metadata.get("source", "未知來源")
            chapter = doc.metadata.get("chapter", "")
            score_tag = f" [相關度: {doc.metadata.get('rerank_score'):.2f}]" if "rerank_score" in doc.metadata else ""
            header = f"[文檔 {i} 來源: 《{source}》" + (f" - {chapter}]" if chapter else "]") + f"{score_tag}"
            chunk = f"{header}\n{doc.page_content}\n\n"
            chunk_tokens = self._estimate_tokens(chunk)

            if accumulated_tokens + chunk_tokens > max_tokens:
                break

            formatted_parts.append(chunk)
            accumulated_tokens += chunk_tokens

        return "".join(formatted_parts).strip()

    # ---------------------------------------------------------------- 問答鏈與目錄感知
    def _build_qa_chain(self, docs_context: str, catalog_context: str, use_thinking: bool):
        """構建同時具備文獻片段與全庫目錄認知的問答鏈。"""
        if use_thinking:
            template = """你是一位博學的書籍助手。請仔細研讀以下參考文獻與書庫清單並回答問題。

【當前書庫完整書單清單】：
{catalog}

【檢索文獻片段】：
{context}

規則：
1. 若問題涉及「有哪些書」、「推薦書籍」、「書籍分類（如小說、心理學）」等全庫概覽問題，請優先結合【當前書庫完整書單清單】給出精確解答。
2. 請先進行深入的邏輯推理，將思考與分析過程完整放在 <thinking> 和 </thinking> 標籤中。
3. 思考結束後，在 <answer> 和 </answer> 標籤中輸出條理分明的最終回答。
4. 若有引用文獻內容，請標註引用來源。

【問題】：
{question}
"""
        else:
            template = """你是一位博學的書籍助手。請仔細研讀以下參考文獻與書庫清單並回答問題。

【當前書庫完整書單清單】：
{catalog}

【檢索文獻片段】：
{context}

規則：
1. 若問題涉及「有哪些書」、「書籍分類（如小說、散文、工具書）」等問題，請根據【當前書庫完整書單清單】直接列舉與分類回答。
2. 引用文獻時標註來源書籍。
3. 保持格式清晰、重點突出。

【問題】：
{question}
回答：
"""
        prompt = ChatPromptTemplate.from_template(template)
        return (
            {"context": lambda _: docs_context, "catalog": lambda _: catalog_context, "question": RunnablePassthrough()}
            | prompt
            | self.llm
            | StrOutputParser()
        )

    # ---------------------------------------------------------------- 查詢入口
    def query(self, question: str, use_thinking: bool = False) -> Dict[str, Any]:
        if not self.is_ready:
            return {
                "answer": "系統尚未就緒，請檢查向量資料庫或 LLM 連線設定。",
                "sources": [],
                "is_stat_query": False,
                "log": "Engine not ready",
                "thinking_process": "",
            }

        # 純統計類問題分流
        stat_exact_keywords = ["幾本書", "多少本書", "統計數量", "總共幾本", "庫藏數量"]
        if any(kw in question for kw in stat_exact_keywords):
            return self._handle_stat_query()

        return self._handle_rag_query(question, use_thinking)

    def _handle_stat_query(self) -> Dict[str, Any]:
        stats = self.get_library_stats()
        if "error" in stats:
            return {
                "answer": f"獲取統計資訊失敗: {stats['error']}",
                "sources": [],
                "is_stat_query": True,
                "log": "統計查詢失敗",
                "thinking_process": "",
            }
        book_list = "\n".join(f"- 📖 {b}" for b in stats["book_list"])
        answer = (
            f"目前知識庫共收錄 **{stats['book_count']}** 本書籍/文件，"
            f"累積 **{stats['total_chunks']}** 個知識片段。\n\n"
            f"**收錄書單：**\n{book_list if book_list else '（目前書庫為空）'}"
        )
        return {
            "answer": answer,
            "sources": [],
            "is_stat_query": True,
            "log": "執行統計模式查詢",
            "thinking_process": "",
        }

    def _handle_rag_query(self, question: str, use_thinking: bool) -> Dict[str, Any]:
        start_time = time.time()

        # 1. 取得全庫書單目錄（讓 LLM 具備全庫視野）
        stats = self.get_library_stats()
        book_list = stats.get("book_list", [])
        catalog_str = "\n".join([f"- 《{b}》" for b in book_list]) if book_list else "（目前書庫無任何書籍）"

        # 2. 執行兩階段混合檢索 (含簡繁對齊與 Metadata 增強)
        source_docs, retrieval_logs = self._hybrid_search(question)

        formatted_context = self._format_docs_with_token_limit(source_docs)
        chain = self._build_qa_chain(formatted_context, catalog_str, use_thinking)

        try:
            raw_response = chain.invoke(question)
        except Exception as e:
            logger.error(f"[Engine] 問答生成失敗: {e}", exc_info=True)
            return {
                "answer": f"生成回答時發生異常: {e}",
                "sources": source_docs,
                "is_stat_query": False,
                "log": "\n".join(retrieval_logs) + f"\n生成錯誤: {e}",
                "thinking_process": "",
            }

        thinking_process = ""
        final_answer = raw_response

        if use_thinking:
            think_match = re.search(r'<thinking>(.*?)</thinking>', raw_response, re.DOTALL)
            ans_match = re.search(r'<answer>(.*?)</answer>', raw_response, re.DOTALL)
            if think_match:
                thinking_process = think_match.group(1).strip()
            if ans_match:
                final_answer = ans_match.group(1).strip()

        elapsed = time.time() - start_time
        retrieval_logs.append(f"【端到端總耗時】: {elapsed:.2f}s (檢索重排 + LLM 推論)")

        return {
            "answer": final_answer,
            "sources": source_docs,
            "is_stat_query": False,
            "log": "\n".join(retrieval_logs),
            "thinking_process": thinking_process,
        }

    # ---------------------------------------------------------------- 深度綜整與管理
    def generate_deep_synthesis(self, question: str, retrieved_docs: List[Any]) -> Dict[str, Any]:
        if not self.synthesizer:
            return {"status": "error", "content": "深度綜整引擎未就緒", "source_count": 0}
        return self.synthesizer.generate_comprehensive_report(question=question, context_docs=retrieved_docs)

    def get_library_stats(self) -> Dict[str, Any]:
        try:
            if not self.vectorstore:
                return {"book_count": 0, "book_list": [], "total_chunks": 0}
            collection = self.vectorstore._collection
            results = collection.get(include=["metadatas"])
            sources = set()
            total_chunks = len(results.get("ids", []))

            if results.get("metadatas"):
                for meta in results["metadatas"]:
                    if meta:
                        name = meta.get("filename") or meta.get("source")
                        if name:
                            sources.add(os.path.basename(name))

            return {
                "book_count": len(sources),
                "book_list": sorted(list(sources)),
                "total_chunks": total_chunks,
            }
        except Exception as e:
            logger.error(f"[Engine] 讀取統計失敗: {e}", exc_info=True)
            return {"error": str(e)}

    def get_book_list_with_chunk_counts(self) -> List[Dict[str, Any]]:
        try:
            if not self.vectorstore:
                return []
            collection = self.vectorstore._collection
            results = collection.get(include=["metadatas"])
            books: Dict[str, Dict[str, Any]] = {}

            if results.get("metadatas"):
                for meta in results["metadatas"]:
                    if not meta:
                        continue
                    source = meta.get("source", "未知來源")
                    if source not in books:
                        filename = meta.get("filename", os.path.basename(source))
                        file_type = meta.get("file_type", "")
                        if not file_type:
                            ext = os.path.splitext(filename)[1].lower().lstrip(".")
                            file_type = ext if ext in ("pdf", "epub", "txt") else "unknown"

                        books[source] = {
                            "source": source,
                            "filename": filename,
                            "chunk_count": 0,
                            "file_type": file_type,
                            "ocr_quality": meta.get("ocr_quality", 0),
                            "ocr_level": meta.get("ocr_level", "unknown"),
                        }
                    books[source]["chunk_count"] += 1

            return sorted(books.values(), key=lambda x: x["filename"])
        except Exception as e:
            logger.error(f"[Engine] 獲取詳細書籍列表失敗: {e}", exc_info=True)
            return [{"error": str(e)}]

    def get_book_chunks(self, source: str) -> List[Dict[str, Any]]:
        try:
            if not self.vectorstore:
                return []
            collection = self.vectorstore._collection
            results = collection.get(include=["metadatas", "documents"])
            chunks = []

            if results.get("metadatas") and results.get("documents"):
                for meta, doc in zip(results["metadatas"], results["documents"]):
                    if meta and meta.get("source") == source:
                        chunks.append({"content": doc, "metadata": meta})
            return chunks
        except Exception as e:
            logger.error(f"[Engine] 讀取書籍片段失敗 ({source}): {e}", exc_info=True)
            return [{"error": str(e)}]

    def delete_book_by_source(self, source: str) -> Dict[str, Any]:
        try:
            if not self.vectorstore:
                return {"status": "error", "message": "向量資料庫未初始化"}
            collection = self.vectorstore._collection
            results = collection.get(include=["metadatas"])

            ids_to_delete = []
            if results.get("metadatas"):
                for meta, doc_id in zip(results["metadatas"], results["ids"]):
                    if meta and meta.get("source") == source:
                        ids_to_delete.append(doc_id)

            if not ids_to_delete:
                return {"status": "error", "message": f"找不到來源為 '{source}' 的文檔"}

            batch_size = self.config.DB_BATCH_SIZE
            for i in range(0, len(ids_to_delete), batch_size):
                batch = ids_to_delete[i : i + batch_size]
                collection.delete(ids=batch)

            logger.info(f"[Engine] 已刪除書籍 '{source}' 共 {len(ids_to_delete)} 個片段")
            self.rebuild_bm25()
            return {"status": "success", "deleted_count": len(ids_to_delete)}
        except Exception as e:
            logger.error(f"[Engine] 刪除書籍失敗 ({source}): {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    def clear_all_library_data(self) -> Dict[str, Any]:
        try:
            if not self.vectorstore:
                return {"status": "error", "message": "向量資料庫未初始化"}
            collection = self.vectorstore._collection
            all_ids = collection.get().get("ids", [])

            if not all_ids:
                return {"status": "success", "deleted_count": 0}

            batch_size = self.config.DB_BATCH_SIZE
            for i in range(0, len(all_ids), batch_size):
                batch = all_ids[i : i + batch_size]
                collection.delete(ids=batch)

            self.bm25_retriever = None
            logger.info(f"[Engine] 已清除全庫資料共 {len(all_ids)} 筆片段")
            return {"status": "success", "deleted_count": len(all_ids)}
        except Exception as e:
            logger.error(f"[Engine] 清空資料庫異常: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}