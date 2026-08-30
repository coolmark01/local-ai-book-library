# -*- coding: utf-8 -*-
"""
Obsidian 筆記生成引擎 (obsidian_engine.py)
==========================================
職責：將檢索到的文獻片段轉化為符合 Obsidian 生態規範的結構化 Markdown 筆記。
支援 4 種專業筆記模式：
  1. deep_dive  : 單書精讀 / 深度申論（論證鏈條、核心脈絡、章節剖析、落地指南）
  2. synthesis  : 多書交叉 / 主題綜整（不同文獻觀點碰撞、互補與分歧對比）
  3. atomic     : 原子概念卡片 (Zettelkasten)（精準定義、運作機制、關聯網絡）
  4. critique   : 批判性剖析 / 盲點檢視（核心論點、突破優勢、局限與適用邊界）
"""

import re
import logging
from typing import List, Dict, Any, Optional, Union
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.documents import Document

logger = logging.getLogger("LibraryLogger")

# ===================================================================
# 筆記模板定義
# ===================================================================

PROMPT_SYNTHESIS = """你是一位知識管理與跨學科綜整專家。
你的任務是將使用者提供的多篇文獻片段，轉化為一篇具備高度連結性、多視角對話的 Obsidian 交叉綜整筆記。

【Obsidian 語法規範 — 請嚴格遵守】
1. 雙向連結：文中出現的核心概念、專有名詞、書名、理論或關鍵人物，必須使用 [[雙向連結]] 包覆（例如：[[原子習慣]]、[[心流理論]]）。
2. 重點高亮：最具啟發性的金句或核心結論，使用 ==高亮== 標記。
3. 提示區塊：使用 > [!abstract]、> [!info]、> [!tip] 等 Callout 語法凸顯重要結論。

【輸出模板 — 嚴格按照以下格式輸出，不加任何前言或結語】

---
tags:
{tags_yaml}
---
# 🌐 主題綜整：{topic}

> [!abstract] 核心綜述
> [請用 2~3 句話提煉跨文獻對此主題的核心共識與本質洞察]

## 💡 核心知識體系
[詳細知識綜整。融會貫通不同來源。使用 ==高亮== 標記重點，關鍵概念加上 [[雙向連結]]]

## 🔄 跨文獻觀點勾稽與對話
- **[[核心概念 A]]**：在 [[來源1]] 中強調...；而 [[來源2]] 則從...角度進行補充/提出不同觀點。
- **[[核心概念 B]]**：...

## 🔗 知識網絡與延伸探索
- **關聯文獻節點**：
{source_nodes}
- **未來探索概念 (AI 建議)**：
  - [[建議探索主題 1]]：[簡要說明原因]
  - [[建議探索主題 2]]：[簡要說明原因]
"""

PROMPT_DEEP_DIVE = """你是一位深度閱讀導師與學術書評家。
你的任務是針對特定書籍與議題，撰寫一篇邏輯嚴密、結構清晰的 Obsidian 單書精讀與深度申論筆記。

【Obsidian 語法規範 — 請嚴格遵守】
1. 雙向連結：核心概念、關鍵名詞、理論架構必須使用 [[雙向連結]] 包覆。
2. 重點高亮：書中核心洞見、金句論點使用 ==高亮== 標記。
3. 提示區塊：使用 > [!abstract]、> [!quote]、> [!tip] 凸顯重點。

【輸出模板 — 嚴格按照以下格式輸出，不加任何前言或結語】

---
tags:
{tags_yaml}
---
# 📘 深度導讀與申論：{topic}

> [!abstract] 核心論點提煉
> [用精煉文字總結本書/本章針對該議題的核心主張與最高認知模型]

## 🧠 底層邏輯與論證體系
[深入剖析作者的核心論證鏈條。作者如何推演？立論依據為何？使用 ==高亮== 與 [[雙向連結]]]

## 📑 關鍵章節剖析與深度申論
- **[[關鍵維度一]]**：深入探討書籍中的具體概念、實驗數據或案例分析。
- **[[關鍵維度二]]**：展開進一步的推演與作者獨特視角的解析。

## 🎯 實踐落地與行動指南
1. **[步驟一]**：具體可落地的日常行動或決策原則。
2. **[步驟二]**：思維轉換的關鍵觸發點。

## 💎 金句摘錄與來源節點
> [!quote] 核心金句
> [摘錄或提煉 1~2 句最具穿透力的核心原話/觀點]

- **來源文獻節點**：
{source_nodes}
"""

PROMPT_ATOMIC = """你是一位卡片盒筆記法 (Zettelkasten) 實踐專家。
你的任務是從提供的文獻中，提煉出一個單一、聚焦且具備自解釋性的「原子概念卡片 (Atomic Note)」。

【Obsidian 語法規範 — 請嚴格遵守】
1. 雙向連結：涉及的上下游概念、關聯名詞使用 [[雙向連結]]。
2. 重點高亮：概念核心定義使用 ==高亮==。
3. 提示區塊：使用 > [!info] 進行精確定義。

【輸出模板 — 嚴格按照以下格式輸出，不加任何前言或結語】

---
tags:
{tags_yaml}
---
# 💡 [[{topic}]]

> [!info] 核心定義
> ==[用 1~2 句話給出該概念精確、獨立的本質定義]==

## ⚙️ 運作機制與核心原理
[該概念如何運作？其背後的心理學、物理學或管理學原理是什麼？]

## 🛠️ 應用場景與實例
- **[場景一]**：具體生活、工作或思考中的應用示範。
- **[場景二]**：常見誤區與反向思考。

## 🔗 上下游關聯網絡
- **上位概念 (Parent)**：[[概念1]]
- **並列/相關概念 (Related)**：[[概念2]], [[概念3]]
- **來源文獻**：
{source_nodes}
"""

PROMPT_CRITIQUE = """你是一位具備批判性思維的學者與書評家。
你的任務是跳脫盲從，對文獻中的核心主張進行客觀剖析、論證檢驗與局限性申論。

【Obsidian 語法規範 — 請嚴格遵守】
1. 雙向連結：專有名詞、對立學派、理論使用 [[雙向連結]]。
2. 重點高亮：突破性優勢與核心盲點使用 ==高亮==。
3. 提示區塊：使用 > [!warning] 凸顯局限性與邊界條件。

【輸出模板 — 嚴格按照以下格式輸出，不加任何前言或結語】

---
tags:
{tags_yaml}
---
# ⚖️ 批判性剖析：{topic}

> [!abstract] 觀點評述綜覽
> [簡述作者核心主張，並給出客觀的批判性評價]

## 🌟 核心貢獻與理論突破
[分析該論點在哪些方面提供了革命性的洞察？解決了什麼痛點？使用 ==高亮== 標記]

## ⚠️ 局限性、盲點與邊界條件
> [!warning] 潛在盲點與適用邊界
> [指出該理論在什麼條件下會失效？有哪些未考慮的變數或時代局限？]

- **[盲點一]**：論據不足或推論過度之處。
- **[盲點二]**：實際執行可能面臨的阻礙與反作用力。

## 🔄 辯證思考與互補觀點
- 對比其他學派或文獻的可能反駁：[[對立觀點/學派]]。

## 🔗 參考文獻
{source_nodes}
"""


class ObsidianEngine:
    """Obsidian 筆記生成引擎"""

    def __init__(self, llm):
        logger.info("[ObsidianEngine] 正在初始化多模式 Obsidian 筆記生成引擎...")
        self.llm = llm
        self.chains = {
            "synthesis": self._build_chain(PROMPT_SYNTHESIS),
            "deep_dive": self._build_chain(PROMPT_DEEP_DIVE),
            "atomic": self._build_chain(PROMPT_ATOMIC),
            "critique": self._build_chain(PROMPT_CRITIQUE),
        }
        logger.info("[ObsidianEngine] 筆記生成引擎（含 4 種模式）初始化完成")

    def _build_chain(self, template_str: str):
        prompt = ChatPromptTemplate.from_messages([
            ("system", template_str),
            ("human", "主題/議題：{topic}\n\n以下是相關文獻參考片段：\n\n{context}\n\n請直接輸出符合規範的 Obsidian Markdown 筆記：")
        ])
        return prompt | self.llm | StrOutputParser()

    def generate_obsidian_note(
        self,
        topic: str,
        docs: List[Union[Document, Dict[str, Any], str]],
        note_type: str = "synthesis",
        custom_tags: Optional[List[str]] = None,
        max_context_chars: int = 14000
    ) -> Dict[str, Any]:
        """
        根據主題、檢索片段與選定模式生成 Obsidian 筆記。

        參數：
            topic: 筆記主題或概念名
            docs: 檢索到的文獻片段列表
            note_type: "synthesis" | "deep_dive" | "atomic" | "critique"
            custom_tags: 使用者附加標籤
            max_context_chars: 上下文字元截斷上限

        回傳：
            dict: {"status": "success" | "error", "content": str, "source_count": int}
        """
        logger.info(f"[ObsidianEngine] 開始生成筆記 | 模式: '{note_type}', 主題: '{topic}', 片段數: {len(docs)}")

        if not docs:
            logger.warning("[ObsidianEngine] 無文獻片段可供轉換")
            return {
                "status": "error",
                "content": "未提供相關文獻片段，無法生成結構化筆記。",
                "source_count": 0
            }

        # 模式標籤配置
        mode_tag_map = {
            "synthesis": ["AI知識庫", "跨書綜整", "主題閱讀"],
            "deep_dive": ["AI知識庫", "單書精讀", "深度申論"],
            "atomic": ["AI知識庫", "原子筆記", "卡片盒"],
            "critique": ["AI知識庫", "批判性思考", "書評剖析"],
        }
        base_tags = mode_tag_map.get(note_type, ["AI知識庫", "讀書筆記"])

        if custom_tags:
            for t in custom_tags:
                clean_t = t.strip().lstrip("#")
                if clean_t and clean_t not in base_tags:
                    base_tags.append(clean_t)

        tags_yaml = "\n".join([f"  - #{tag}" for tag in base_tags])

        # 組合文獻片段與來源節點
        context_parts = []
        source_names = set()

        for i, doc in enumerate(docs, start=1):
            if isinstance(doc, Document):
                src = doc.metadata.get("filename") or doc.metadata.get("source", f"文件 {i}")
                chapter = doc.metadata.get("chapter", "")
                src_clean = src.split("/")[-1].split("\\")[-1]
                source_names.add(src_clean)
                header = f"【來源 {i}：{src_clean}" + (f" - {chapter}】" if chapter else "】")
                context_parts.append(f"{header}\n{doc.page_content}")
            elif isinstance(doc, dict):
                src = doc.get("metadata", {}).get("source", f"文件 {i}")
                src_clean = str(src).split("/")[-1].split("\\")[-1]
                source_names.add(src_clean)
                content = doc.get("content", str(doc))
                context_parts.append(f"【來源 {i}：{src_clean}】\n{content}")
            else:
                context_parts.append(f"【來源 {i}】\n{str(doc)}")

        combined_context = "\n\n---\n\n".join(context_parts)
        if len(combined_context) > max_context_chars:
            combined_context = combined_context[:max_context_chars] + "\n\n[... 後續參考內容已截斷 ...]"
            logger.warning(f"[ObsidianEngine] 上下文已截斷至 {max_context_chars} 字元")

        source_nodes = "\n".join([f"  - [[{name}]]" for name in sorted(list(source_names))])
        if not source_nodes:
            source_nodes = "  - [[書庫文獻]]"

        # 選擇生成鏈
        target_chain = self.chains.get(note_type, self.chains["synthesis"])

        try:
            result = target_chain.invoke({
                "topic": topic,
                "context": combined_context,
                "tags_yaml": tags_yaml,
                "source_nodes": source_nodes
            })

            if not result or len(result.strip()) < 30:
                return {
                    "status": "error",
                    "content": "AI 生成內容過短，請重試或增加選定文獻片段。",
                    "source_count": len(docs)
                }

            return {
                "status": "success",
                "content": result.strip(),
                "source_count": len(docs)
            }

        except Exception as e:
            logger.error(f"[ObsidianEngine] 筆記生成異常: {e}", exc_info=True)
            return {
                "status": "error",
                "content": f"生成筆記時發生錯誤：{str(e)}",
                "source_count": len(docs)
            }