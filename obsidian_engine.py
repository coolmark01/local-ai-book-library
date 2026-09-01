# -*- coding: utf-8 -*-
"""
Obsidian 專題筆記生成引擎 (obsidian_engine.py)
==============================================
負責：
  1. 提供 4 大第二大腦筆記模式生成：
     - deep_dive (單書精讀申論)
     - synthesis (多書交叉綜整)
     - atomic_card (原子概念卡片 / Zettelkasten)
     - critique (批判思維檢視)
  2. 自動構建 Obsidian 雙向連結 [[Wikilinks]]、Callout 區塊與結構化 Markdown
  3. 整合 LLM 提示詞工程與上下文文獻切塊拼接
"""

import re
import logging
from typing import List, Dict, Any, Optional
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger("LibraryLogger")


# ===================================================================
# 4 大筆記架構 System Prompt
# ===================================================================
SYSTEM_PROMPTS = {
    "deep_dive": """你是一位頂級個人知識管理（PKM）與深度閱讀研究專家。
你的任務是依據提供的書籍內文片段，針對指定主題撰寫一份結構嚴謹、論證深刻的「單書精讀申論筆記（Single-Book Deep Dive）」。

格式規範要求：
1. 使用標準 Markdown，並充分運用 Obsidian 語法（包含 `[[雙向連結]]`、`> [!abstract]` / `> [!tip]` Callout 區塊、`==重點高亮==`）。
2. 在重要專業名詞、核心人物、關鍵概念周圍主動加上雙向連結語法，如 `[[邊際安全]]`、`[[第一性原理]]`。
3. 結構大綱：
   - `# [[主題]] — 深度精讀申論`
   - `> [!abstract] 核心思想概括（200 字內提煉底層邏輯）`
   - `## 1. 脈絡梳理與底層機制推導`
   - `## 2. 關鍵論點解構與文獻證據`
   - `## 3. 落地行動指南與實踐檢核清單`
   - `## 4. 延伸連結與關鍵概念網絡`
4. 語言風格深刻客觀，拒絕空話套話，每一項論點都必須緊密依託書籍上下文。""",

    "synthesis": """你是一位跨學科知識綜整專家與認知科學家。
你的任務是針對提供的多本書籍內文片段，跨越文本邊界，撰寫一份高維度的「多書交叉綜整研究筆記（Cross-Book Synthesis）」。

格式規範要求：
1. 使用標準 Markdown 與 Obsidian 語法（包含 `[[雙向連結]]`、`> [!summary]` Callout 區塊、Markdown 對照表格）。
2. 在跨書關鍵概念加上 `[[雙向連結]]`。
3. 結構大綱：
   - `# [[主題]] — 跨書交叉綜整研究`
   - `> [!summary] 綜整全景視圖`
   - `## 1. 跨文本觀點對照矩陣（請用 Markdown Table 呈現不同書籍對此主題的視角、共識與分歧）`
   - `## 2. 共通底層規律與第一性原理萃取`
   - `## 3. 理論框架衝突與邊界條件探討`
   - `## 4. 整合型綜合決策模型`
   - `## 5. 跨學科概念網絡（列出 5~8 個 [[雙向連結]] 概念卡）`
4. 必須明確標註不同書籍的觀點來源（如《書名 A》主張...而《書名 B》補充...）。""",

    "atomic_card": """你是一位卡片盒筆記法（Zettelkasten）實踐大師。
你的任務是依據書籍片段，提煉出一張高度聚焦、單一職責、可自由組合的「原子概念卡片（Atomic Concept Card）」。

格式規範要求：
1. 使用標準 Markdown 與 Obsidian 語法（包含 `> [!quote]`、`> [!important]` Callout 區塊、`[[雙向連結]]`）。
2. 結構大綱：
   - `# [[概念名稱]] (Atomic Card)`
   - `> [!quote] 一句話本質定義`
   - `## 1. 運作機制與核心原理（How & Why）`
   - `## 2. 反直覺洞察（突破常規認知的視角）`
   - `## 3. 應用場景與邊界限制（何時適用 / 何時失效）`
   - `## 4. 上下層雙向連結（上位概念、關聯概念、下位概念的 [[Wikilinks]]）`
3. 篇幅精煉扎實，字字珠璣，聚焦於概念本質。""",

    "critique": """你是一位嚴謹的邏輯學家與獨立批判思維學者。
你的任務是依據書籍內文，針對作者的特定觀點進行深度審視，撰寫一份「批判思維與邊界檢視筆記（Critical Review）」。

格式規範要求：
1. 使用標準 Markdown 與 Obsidian 語法（包含 `> [!warning]` / `> [!question]` Callout 區塊、`[[雙向連結]]`）。
2. 結構大綱：
   - `# [[主題]] — 批判思維與邊界檢視`
   - `> [!warning] 核心論點的前提假設檢驗`
   - `## 1. 潛在認知偏誤與論證邏輯盲點`
   - `## 2. 理論失效的極端情境與潛在反例`
   - `## 3. 時代侷限性與環境變遷帶來的挑戰`
   - `## 4. 補充視角與修正版思維模型`
   - `## 5. 待檢驗問題清單（向該理論提出的 3 個尖銳問題）`
3. 保持客觀理性，既指出其價值，亦點明其邊界。"""
}


class ObsidianEngine:
    """Obsidian 專題筆記生成引擎"""

    def __init__(self, llm: Any = None):
        """
        初始化引擎。
        :param llm: LangChain 相容之語言模型實例 (如 ChatOllama 或雲端 LLM)
        """
        self.llm = llm

    def _format_context_docs(self, docs: List[Any]) -> str:
        """將檢索到的文獻片段格式化為結構化文本。"""
        formatted_snippets = []
        for i, d in enumerate(docs, start=1):
            if hasattr(d, "page_content"):
                content = d.page_content.strip()
                meta = d.metadata if hasattr(d, "metadata") else {}
            elif isinstance(d, dict):
                content = (d.get("content") or d.get("page_content") or "").strip()
                meta = d.get("metadata", {})
            else:
                content = str(d).strip()
                meta = {}

            book_name = meta.get("filename") or meta.get("source") or "書籍資料"
            chapter = meta.get("chapter", "")
            chap_str = f" (章節: {chapter})" if chapter else ""
            
            snippet = f"【來源文獻 {i}】《{book_name}》{chap_str}\n{content}"
            formatted_snippets.append(snippet)

        return "\n\n---\n\n".join(formatted_snippets)

    def generate_note(
        self,
        mode: str,
        topic: str,
        books: List[str],
        context_docs: List[Any],
        **kwargs
    ) -> str:
        """
        核心筆記生成入口。
        :param mode: 筆記模式 ('deep_dive', 'synthesis', 'atomic_card', 'critique')
        :param topic: 探討主題 / 核心問題
        :param books: 關聯目標書籍列表
        :param context_docs: 檢索召回之文獻切塊清單
        :return: 生成的 Obsidian Markdown 筆記文字
        """
        if not self.llm:
            raise ValueError("未配置可用的 LLM 語言模型實例")

        system_prompt = SYSTEM_PROMPTS.get(mode, SYSTEM_PROMPTS["deep_dive"])
        context_text = self._format_context_docs(context_docs)
        books_str = "、".join([f"《{b}》" for b in books])

        user_prompt = f"""請依據以下提供的書籍內文片段，針對主題撰寫高品質的 Obsidian 筆記：

【研究主題】：{topic}
【目標書籍】：{books_str}

【書籍內文資料庫】：
{context_text}

請嚴格依照規範的大綱結構進行深度闡述，多使用 `[[雙向連結]]` 與 Callout 區塊，輸出完整的 Markdown 筆記內容："""

        try:
            # 兼容 LangChain 各版本呼叫
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]

            if hasattr(self.llm, "invoke"):
                response = self.llm.invoke(messages)
                content = response.content if hasattr(response, "content") else str(response)
            elif hasattr(self.llm, "predict_messages"):
                response = self.llm.predict_messages(messages)
                content = response.content if hasattr(response, "content") else str(response)
            elif callable(self.llm):
                full_prompt = f"{system_prompt}\n\n{user_prompt}"
                content = str(self.llm(full_prompt))
            else:
                raise RuntimeError("LLM 實例不支援標準呼叫方法")

            return content.strip()

        except Exception as e:
            logger.error(f"[ObsidianEngine] 筆記生成失敗: {e}", exc_info=True)
            raise RuntimeError(f"語言模型生成筆記時發生錯誤：{e}")

    # 相容舊版別名方法
    def generate_obsidian_note(self, *args, **kwargs) -> str:
        return self.generate_note(*args, **kwargs)

    def generate_deep_dive(self, topic: str, book: str, context_docs: List[Any]) -> str:
        return self.generate_note(mode="deep_dive", topic=topic, books=[book], context_docs=context_docs)

    def generate_synthesis(self, topic: str, books: List[str], context_docs: List[Any]) -> str:
        return self.generate_note(mode="synthesis", topic=topic, books=books, context_docs=context_docs)