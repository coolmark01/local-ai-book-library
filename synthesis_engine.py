# -*- coding: utf-8 -*-
"""
深度綜整引擎 (synthesis_engine.py)
==================================
職責：對檢索到的多維度文獻片段進行跨章節、跨書籍的深度交叉比對與論點綜整。
具備結構化 Markdown 輸出約束與長文本安全截斷保護。
"""

import logging
from typing import List, Dict, Any, Union
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.documents import Document

logger = logging.getLogger("LibraryLogger")

SYNTHESIS_SYSTEM_PROMPT = """你是一位精通跨領域文獻分析與知識體系建構的資深研究員。
你的任務是仔細研讀使用者提供的多篇參考資料片段，針對使用者的問題進行深度交叉比對、論點整合與邏輯推演。

【輸出結構規範 — 請嚴格按照以下 Markdown 格式輸出】
# 深度綜整分析：{question}

## 📌 核心結論與洞察
- 用 2~3 個重點條列，直接給出最核心的總結性答案與結論。

## 🔍 多維度觀點剖析與交叉論證
- **[核心論點/維度一]**：結合參考文獻深入剖析。若不同文獻有互補或對立觀點，請明確指出（例如：[來源1] 與 [來源2] 的呼應或分歧）。
- **[核心論點/維度二]**：提供進一步的理論支撐、機制分析或具體案例。

## 💡 實踐應用與落地建議
1. 具體可行的實踐步驟或思考方向。
2. 注意事項或潛在盲點。

【生成規則】
1. 嚴格基於提供的參考資料進行綜整，論點需有憑有據。
2. 保持專業、客觀、邏輯嚴密且文字流暢。
3. 適當使用粗體標記關鍵概念。
4. 若文獻資訊有限，請先綜整已知內容，並於末尾明確指出資訊缺口。
"""


class SynthesisEngine:
    """深度綜整引擎：針對檢索片段生成結構化長篇綜整報告。"""

    def __init__(self, llm):
        logger.info("[SynthesisEngine] 正在初始化深度綜整引擎...")
        self.llm = llm
        self.chain = self._build_synthesis_chain()
        logger.info("[SynthesisEngine] 深度綜整引擎初始化完成")

    def _build_synthesis_chain(self):
        """建構具備結構化輸出的 LangChain 綜整鏈。"""
        prompt = ChatPromptTemplate.from_messages([
            ("system", SYNTHESIS_SYSTEM_PROMPT),
            ("human", "【待分析問題】：\n{question}\n\n【參考資料片段】：\n{context}\n\n請開始進行深度綜整分析：")
        ])
        return prompt | self.llm | StrOutputParser()

    def generate_comprehensive_report(
        self,
        question: str,
        context_docs: List[Union[Document, Dict[str, Any], str]],
        max_context_chars: int = 14000
    ) -> Dict[str, Any]:
        """
        生成深度綜整報告。

        參數：
            question: 使用者提問
            context_docs: 檢索到的文獻片段列表
            max_context_chars: 最大上下文輸入字元保護閾值

        回傳：
            dict: {"status": "success" | "error", "content": str, "source_count": int}
        """
        logger.info(f"[SynthesisEngine] 開始綜整任務，問題: '{question}', 參考片段數: {len(context_docs)}")

        if not context_docs:
            logger.warning("[SynthesisEngine] 參考資料片段為空")
            return {
                "status": "error",
                "content": "未提供任何參考資料片段，無法進行深度綜整。",
                "source_count": 0
            }

        # 格式化文獻片段
        context_parts = []
        for i, doc in enumerate(context_docs, start=1):
            if isinstance(doc, Document):
                src = doc.metadata.get("filename") or doc.metadata.get("source", f"文件 {i}")
                chapter = doc.metadata.get("chapter", "")
                header = f"【來源 {i}：{src}" + (f" - {chapter}】" if chapter else "】")
                context_parts.append(f"{header}\n{doc.page_content}")
            elif isinstance(doc, dict):
                src = doc.get("metadata", {}).get("source", f"文件 {i}")
                content = doc.get("content", str(doc))
                context_parts.append(f"【來源 {i}：{src}】\n{content}")
            else:
                context_parts.append(f"【來源 {i}】\n{str(doc)}")

        combined_context = "\n\n---\n\n".join(context_parts)

        # 上下文長度保護（避免超出模型 Context Window）
        if len(combined_context) > max_context_chars:
            combined_context = combined_context[:max_context_chars] + "\n\n[... 後續文獻內容因長度限制已省略 ...]"
            logger.warning(f"[SynthesisEngine] 上下文超過閾值，已截斷至 {max_context_chars} 字元")

        try:
            response = self.chain.invoke({
                "question": question,
                "context": combined_context
            })

            if not response or len(response.strip()) < 20:
                logger.warning("[SynthesisEngine] 模型回傳內容過短或為空")
                return {
                    "status": "error",
                    "content": "AI 生成之綜整內容不完整，請嘗試重新執行。",
                    "source_count": len(context_docs)
                }

            logger.info(f"[SynthesisEngine] 綜整完成，產出長度: {len(response)} 字元")
            return {
                "status": "success",
                "content": response.strip(),
                "source_count": len(context_docs)
            }

        except Exception as e:
            logger.error(f"[SynthesisEngine] 綜整任務異常: {e}", exc_info=True)
            return {
                "status": "error",
                "content": f"綜整分析處理時發生錯誤：{str(e)}",
                "source_count": len(context_docs)
            }