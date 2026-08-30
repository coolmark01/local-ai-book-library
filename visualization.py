# -*- coding: utf-8 -*-
"""
知識圖譜與靈感引擎 (visualization.py)
======================================
負責：
  1. 基於 POS 詞性標註的領域主題思維圖譜構建 (支援自訂圓點尺寸與中斷信號)
  2. 圖譜運算結果本地持久化快取 (graph_cache.json)
  3. 「今日書摘與靈感 (Daily Insights)」隨機檢索與 LLM 金句生成 (含 Document 安全序列化快取)
  4. 生成 Obsidian 互動 HTML 與原生白板檔案 (.canvas)
"""

import os
import re
import json
import math
import random
import logging
from datetime import date
from typing import Dict, Any, List, Set, Tuple, Optional, Callable
from collections import defaultdict, Counter

import jieba
import jieba.posseg as pseg
import jieba.analyse
from langchain_core.documents import Document

logger = logging.getLogger("LibraryLogger")

CACHE_DIR = os.path.dirname(os.path.abspath(__file__))
GRAPH_CACHE_FILE = os.path.join(CACHE_DIR, "graph_cache.json")
INSIGHT_CACHE_FILE = os.path.join(CACHE_DIR, "daily_insight_cache.json")

DOMAIN_PRESETS = {
    "📈 商業與價值投資": [
        "價值投資", "基本價值", "內在價值", "安全邊際", "護城河",
        "總體經濟", "短線", "長線", "資產配置", "現金流",
        "複利", "風險管理", "市場週期", "財報分析", "本益比",
        "通貨膨脹", "利率", "自由現金流", "投資組合", "估值"
    ],
    "🧠 認知與心智模型": [
        "第一性原理", "系統思考", "認知偏誤", "心流", "反脆弱",
        "卡片筆記", "習慣養成", "深度工作", "心智模型", "反思",
        "雙向連結", "知識架構", "注意力", "複利效應", "決策框架"
    ],
    "🚀 商業模式與流量運營": [
        "商業模式", "流量密碼", "短影音", "用戶增長", "精實創業",
        "私域流量", "品牌定位", "轉換率", "變現", "算法推薦",
        "內容營銷", "社群運營", "商業閉環", "護城河", "爆款邏輯"
    ],
    "🌐 全庫通用深度探索": []
}

STRICT_STOP_WORDS = {
    "我的", "我們", "你們", "他們", "自己", "什麼", "這個", "那個", "因為", "所以",
    "如果", "雖然", "但是", "可以", "能夠", "進行", "透過", "通過", "可能", "已經",
    "以及", "一種", "一樣", "地方", "問題", "情況", "時間", "方式", "內容", "相關",
    "因此", "而且", "其中", "這些", "那些", "部分", "大家", "本書", "作者", "章節",
    "pdf", "epub", "txt", "chapter", "page", "來源", "書籍", "目錄", "世界", "事情"
}

VALID_POS_TAGS = {"n", "nr", "nz", "nt", "nw", "eng", "vn"}


class VisualizationEngine:
    """知識圖譜與每日書摘綜合引擎"""

    def __init__(self, vectorstore):
        self.vectorstore = vectorstore

    # ------------------------------------------------------------------ 快取管理
    @staticmethod
    def load_cached_graph() -> Optional[Dict[str, Any]]:
        """讀取本地圖譜快取。"""
        if os.path.exists(GRAPH_CACHE_FILE):
            try:
                with open(GRAPH_CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"[Graph] 讀取圖譜快取失敗: {e}")
        return None

    @staticmethod
    def save_cached_graph(graph_data: Dict[str, Any]):
        """將圖譜運算結果持久化儲存至本地。"""
        try:
            with open(GRAPH_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(graph_data, f, ensure_ascii=False, indent=2)
            logger.info("[Graph] 圖譜快取已成功持久化儲存")
        except Exception as e:
            logger.error(f"[Graph] 儲存圖譜快取失敗: {e}")

    # ------------------------------------------------------------------ 概念抽取
    def _extract_domain_concepts(
        self,
        text: str,
        anchor_seeds: List[str] = None,
        top_n: int = 6
    ) -> List[str]:
        if not text:
            return []

        concepts = []
        seen = set()

        # 1. [[Wikilinks]]
        wikis = re.findall(r'\[\[(.*?)\]\]', text)
        for w in wikis:
            w_clean = w.strip()
            if len(w_clean) >= 2 and w_clean not in STRICT_STOP_WORDS and w_clean not in seen:
                seen.add(w_clean)
                concepts.append(w_clean)

        # 2. 命中主題錨點
        if anchor_seeds:
            for seed in anchor_seeds:
                if seed in text and seed not in seen:
                    seen.add(seed)
                    concepts.append(seed)

        # 3. 詞性過濾 (POS)
        words = pseg.cut(text)
        candidate_words = []
        for word, flag in words:
            word_clean = word.strip()
            if (
                len(word_clean) >= 2
                and flag in VALID_POS_TAGS
                and word_clean not in STRICT_STOP_WORDS
                and not word_clean.isdigit()
            ):
                candidate_words.append(word_clean)

        word_counts = Counter(candidate_words)
        for w, _ in word_counts.most_common(top_n):
            if w not in seen:
                seen.add(w)
                concepts.append(w)

        return concepts[:top_n]

    # ------------------------------------------------------------------ 圖譜構建
    def build_knowledge_graph(
        self,
        domain_name: str = "📈 商業與價值投資",
        custom_anchors: str = "",
        max_concepts: int = 50,
        min_edge_weight: int = 1,
        selected_sources: List[str] = None,
        base_node_size: int = 24,
        progress_callback: Optional[Callable[[float, str], bool]] = None
    ) -> Dict[str, Any]:
        """
        構建知識圖譜。
        支援 base_node_size (圓點大小調整) 與 progress_callback (進度回調與中斷檢查)。
        """
        if not self.vectorstore:
            return {"nodes": [], "edges": [], "hubs": [], "stats": {}}

        anchor_seeds = []
        if custom_anchors.strip():
            anchor_seeds = [a.strip() for a in re.split(r'[,，、\s]+', custom_anchors) if a.strip()]
        elif domain_name in DOMAIN_PRESETS:
            anchor_seeds = DOMAIN_PRESETS[domain_name]

        anchor_seed_set = set(anchor_seeds)

        try:
            collection = self.vectorstore._collection
            results = collection.get(include=["metadatas", "documents"])
            docs = results.get("documents", [])
            metas = results.get("metadatas", [])

            if not docs:
                return {"nodes": [], "edges": [], "hubs": [], "stats": {}}

            book_concepts = defaultdict(Counter)
            concept_books = defaultdict(set)
            concept_total_counts = Counter()
            co_occurrence = Counter()

            total_docs = len(docs)

            for idx, (doc_text, meta) in enumerate(zip(docs, metas), start=1):
                # 中斷檢查與進度更新
                if progress_callback:
                    should_continue = progress_callback(
                        idx / total_docs,
                        f"正在分析文獻片段 ({idx}/{total_docs})..."
                    )
                    if not should_continue:
                        logger.warning("[Graph] 使用者主動中斷圖譜生成")
                        return {"nodes": [], "edges": [], "hubs": [], "stats": {"aborted": True}}

                if not meta or not doc_text:
                    continue
                source = meta.get("filename") or meta.get("source", "未知書籍")
                if selected_sources and source not in selected_sources:
                    continue

                chunk_concepts = self._extract_domain_concepts(
                    doc_text,
                    anchor_seeds=anchor_seeds,
                    top_n=6
                )

                for c in chunk_concepts:
                    boost = 2 if c in anchor_seed_set else 1
                    book_concepts[source][c] += boost
                    concept_books[c].add(source)
                    concept_total_counts[c] += boost

                for i in range(len(chunk_concepts)):
                    for j in range(i + 1, len(chunk_concepts)):
                        c1, c2 = sorted([chunk_concepts[i], chunk_concepts[j]])
                        co_occurrence[(c1, c2)] += 1

            top_concepts = []
            for seed in anchor_seeds:
                if seed in concept_total_counts:
                    top_concepts.append(seed)

            remaining_quota = max_concepts - len(top_concepts)
            other_candidates = [
                c for c, _ in concept_total_counts.most_common()
                if c not in set(top_concepts)
            ]
            top_concepts.extend(other_candidates[:max(remaining_quota, 10)])
            top_concept_set = set(top_concepts)

            nodes = []
            edges = []
            node_ids = set()

            # 1. 書籍圓點大小 (依據 base_node_size 比例計算)
            book_size = int(base_node_size * 1.2)
            for book_name in book_concepts.keys():
                nodes.append({
                    "id": f"book_{book_name}",
                    "label": book_name[:16] + ("..." if len(book_name) > 16 else ""),
                    "title": f"📖 書籍：《{book_name}》<br>涵蓋主題概念數：{len(book_concepts[book_name])}",
                    "group": "book",
                    "shape": "dot",
                    "size": book_size,
                    "color": {
                        "background": "#7c3aed",
                        "border": "#c084fc",
                        "highlight": {"background": "#9333ea", "border": "#ffffff"}
                    },
                    "font": {"color": "#ffffff", "size": 13, "face": "system-ui"}
                })
                node_ids.add(f"book_{book_name}")

            # 2. 概念圓點大小 (依據 base_node_size 進行縮放)
            scale_multiplier = base_node_size / 24.0
            for concept in top_concepts:
                c_id = f"concept_{concept}"
                linked_books = concept_books[concept]
                is_seed = concept in anchor_seed_set
                is_hub = len(linked_books) >= 2 or is_seed
                freq = concept_total_counts[concept]

                # 計算動態圓點尺寸
                min_sz = max(8, int(12 * scale_multiplier))
                max_sz = int(32 * scale_multiplier)
                calc_sz = int(math.log2(freq + 1) * (7 * scale_multiplier))
                node_size = max(min_sz, min(max_sz, calc_sz))

                if is_seed:
                    bg_color = "#e11d48"
                    border_color = "#fda4af"
                elif is_hub:
                    bg_color = "#f59e0b"
                    border_color = "#fcd34d"
                else:
                    bg_color = "#06b6d4"
                    border_color = "#67e8f9"

                node_type_desc = "核心主題錨點" if is_seed else ("跨書樞紐" if is_hub else "衍生概念")

                nodes.append({
                    "id": c_id,
                    "label": concept,
                    "title": f"💡 [{node_type_desc}] [[{concept}]]<br>加權頻次：{freq}<br>關聯書籍：{', '.join(linked_books)}",
                    "group": "seed" if is_seed else ("hub" if is_hub else "concept"),
                    "shape": "dot",
                    "size": node_size,
                    "color": {
                        "background": bg_color,
                        "border": border_color,
                        "highlight": {"background": "#ffffff", "border": bg_color}
                    },
                    "font": {"color": "#f8fafc", "size": 12, "face": "system-ui"}
                })
                node_ids.add(c_id)

                for book in linked_books:
                    b_id = f"book_{book}"
                    if b_id in node_ids:
                        weight = book_concepts[book][concept]
                        edges.append({
                            "from": b_id,
                            "to": c_id,
                            "value": weight,
                            "color": {"color": "rgba(225, 29, 72, 0.4)" if is_seed else "rgba(148, 163, 184, 0.25)"},
                            "title": f"《{book}》提及 [[{concept}]]"
                        })

            for (c1, c2), weight in co_occurrence.items():
                if weight >= min_edge_weight and c1 in top_concept_set and c2 in top_concept_set:
                    is_core_edge = (c1 in anchor_seed_set) or (c2 in anchor_seed_set)
                    edges.append({
                        "from": f"concept_{c1}",
                        "to": f"concept_{c2}",
                        "value": weight,
                        "color": {"color": "rgba(245, 158, 11, 0.5)" if is_core_edge else "rgba(100, 116, 139, 0.2)"},
                        "title": f"[[{c1}]] 與 [[{c2}]] 同步共現 {weight} 次"
                    })

            hubs = [
                {
                    "concept": c,
                    "is_anchor": c in anchor_seed_set,
                    "book_count": len(concept_books[c]),
                    "books": list(concept_books[c]),
                    "total_freq": concept_total_counts[c]
                }
                for c in top_concepts if len(concept_books[c]) >= 2 or c in anchor_seed_set
            ]
            hubs.sort(key=lambda x: (x["is_anchor"], x["book_count"], x["total_freq"]), reverse=True)

            graph_data = {
                "nodes": nodes,
                "edges": edges,
                "hubs": hubs,
                "stats": {
                    "total_books": len(book_concepts),
                    "total_concepts": len(top_concepts),
                    "total_edges": len(edges),
                    "total_hubs": len(hubs),
                    "domain": domain_name
                }
            }

            self.save_cached_graph(graph_data)
            return graph_data

        except Exception as e:
            logger.error(f"[VisualizationEngine] 圖譜構建失敗: {e}", exc_info=True)
            return {"nodes": [], "edges": [], "hubs": [], "stats": {"error": str(e)}}

    # ------------------------------------------------------------------ 今日書摘生成
    def generate_daily_insight(
        self,
        llm,
        target_source: Optional[str] = None,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """生成今日隨機靈感書摘（具備安全 JSON 序列化與每日快取）。"""
        today_str = date.today().strftime("%Y-%m-%d")

        if not force_refresh and os.path.exists(INSIGHT_CACHE_FILE):
            try:
                with open(INSIGHT_CACHE_FILE, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                if cached.get("date") == today_str and (not target_source or cached.get("source") == target_source):
                    logger.info("[Insight] 命中當日書摘快取")
                    raw_docs = cached.get("docs_data", [])
                    reconstructed_docs = [
                        Document(page_content=d.get("content", ""), metadata=d.get("metadata", {}))
                        for d in raw_docs
                    ]
                    cached["docs"] = reconstructed_docs
                    return cached
            except Exception as e:
                logger.warning(f"[Insight] 解析書摘快取失敗: {e}")

        if not self.vectorstore:
            return {"status": "error", "content": "向量資料庫未初始化"}

        seed_queries = [
            "核心底層邏輯與重要觀點", "關鍵思維模型與經典論述", "實踐方法與認知重塑",
            "反直覺的深度洞察", "人生哲理與決策原則", "本質思考與系統規律"
        ]
        chosen_query = random.choice(seed_queries)

        filter_dict = {"source": target_source} if target_source else None
        retrieved_docs = self.vectorstore.similarity_search(chosen_query, k=4, filter=filter_dict)

        if not retrieved_docs:
            return {"status": "error", "content": "書庫中無足夠文獻片段以提煉書摘。"}

        context_parts = []
        source_names = set()
        for i, d in enumerate(retrieved_docs, start=1):
            src = d.metadata.get("filename") or d.metadata.get("source", "書籍")
            src_clean = os.path.basename(src)
            source_names.add(src_clean)
            context_parts.append(f"【文獻 {i} 《{src_clean}》】\n{d.page_content}")

        combined_context = "\n\n".join(context_parts)

        prompt_text = f"""你是一位深邃的讀書思想家。請仔細研讀以下文獻精華片段，為讀者提煉今日的「黃金思想卡片」。

【文獻片段】：
{combined_context}

請嚴格按照以下 Markdown 格式輸出，直接輸出正文：

# 💡 今日靈感書摘：{chosen_query}

> [!quote] 核心金句
> 「[提煉或摘錄一句最具穿透力、發人深省的核心觀點]」
> —— 摘自 {', '.join([f'《{s}》' for s in source_names])}

### 🧠 深度思維模型解讀
[用 200 字左右深入解構該觀點背後的底層規律、邏輯機制與思考方式。使用 ==高亮== 與 [[雙向連結]]]

### 🎯 今日行動落地啟發
1. **[微行動 1]**：日常工作/決策中如何運用。
2. **[微行動 2]**：避免的認知盲點。
"""

        try:
            insight_content = llm.invoke(prompt_text)
            final_text = getattr(insight_content, "content", str(insight_content)).strip()

            serializable_docs = [
                {"content": d.page_content, "metadata": d.metadata}
                for d in retrieved_docs
            ]

            result_to_save = {
                "status": "success",
                "date": today_str,
                "source": target_source or "全庫隨機",
                "sources_list": list(source_names),
                "docs_data": serializable_docs,
                "content": final_text
            }

            with open(INSIGHT_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(result_to_save, f, ensure_ascii=False, indent=2)

            result_to_save["docs"] = retrieved_docs
            return result_to_save
        except Exception as e:
            logger.error(f"[Insight] 生成書摘異常: {e}", exc_info=True)
            return {"status": "error", "content": f"生成書摘失敗: {e}"}

    # ------------------------------------------------------------------ HTML & Canvas
    def generate_vis_html(self, graph_data: Dict[str, Any], height: str = "600px") -> str:
        nodes_json = json.dumps(graph_data.get("nodes", []), ensure_ascii=False)
        edges_json = json.dumps(graph_data.get("edges", []), ensure_ascii=False)

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
            <style type="text/css">
                body {{
                    margin: 0; padding: 0; background-color: #121214;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    overflow: hidden;
                }}
                #graph_container {{
                    width: 100%; height: {height};
                    background: radial-gradient(circle at center, #1b1b22 0%, #0d0d10 100%);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 10px;
                }}
                .legend {{
                    position: absolute; bottom: 12px; left: 14px;
                    background: rgba(18, 18, 20, 0.88);
                    padding: 8px 14px; border-radius: 6px;
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    color: #94a3b8; font-size: 11px; line-height: 1.6;
                    pointer-events: none;
                }}
                .dot {{ display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 5px; }}
            </style>
        </head>
        <body>
            <div id="graph_container"></div>
            <div class="legend">
                <span class="dot" style="background:#7c3aed;"></span>書籍節點 &nbsp;&nbsp;
                <span class="dot" style="background:#e11d48;"></span>主題核心錨點 &nbsp;&nbsp;
                <span class="dot" style="background:#f59e0b;"></span>跨書思維樞紐 &nbsp;&nbsp;
                <span class="dot" style="background:#06b6d4;"></span>衍生概念
            </div>
            <script type="text/javascript">
                const nodes = new vis.DataSet({nodes_json});
                const edges = new vis.DataSet({edges_json});
                const container = document.getElementById('graph_container');
                const data = {{ nodes: nodes, edges: edges }};
                const options = {{
                    nodes: {{
                        shape: 'dot',
                        borderWidth: 1.5,
                        shadow: {{ enabled: true, color: 'rgba(0,0,0,0.7)', size: 8, x: 2, y: 2 }}
                    }},
                    edges: {{
                        width: 1.2,
                        smooth: {{ type: 'continuous', roundness: 0.2 }}
                    }},
                    physics: {{
                        solver: 'forceAtlas2Based',
                        forceAtlas2Based: {{
                            gravitationalConstant: -45,
                            centralGravity: 0.008,
                            springLength: 95,
                            springConstant: 0.07,
                            damping: 0.85
                        }},
                        stabilization: {{ iterations: 130 }}
                    }},
                    interaction: {{
                        hover: true,
                        tooltipDelay: 100,
                        zoomView: true,
                        dragView: true
                    }}
                }};

                const network = new vis.Network(container, data, options);

                network.on("click", function (params) {{
                    if (params.nodes.length > 0) {{
                        const nodeId = params.nodes[0];
                        const connectedNodes = network.getConnectedNodes(nodeId);
                        connectedNodes.push(nodeId);
                        nodes.forEach(function(node) {{
                            if (connectedNodes.includes(node.id)) {{
                                nodes.update({{ id: node.id, opacity: 1.0 }});
                            }} else {{
                                nodes.update({{ id: node.id, opacity: 0.15 }});
                            }}
                        }});
                    }} else {{
                        nodes.forEach(function(node) {{
                            nodes.update({{ id: node.id, opacity: 1.0 }});
                        }});
                    }}
                }});
            </script>
        </body>
        </html>
        """

    def generate_obsidian_canvas(self, graph_data: Dict[str, Any]) -> str:
        nodes = graph_data.get("nodes", [])
        edges = graph_data.get("edges", [])
        canvas_nodes = []
        canvas_edges = []

        total = len(nodes)
        radius = max(380, total * 26)

        for i, node in enumerate(nodes):
            angle = (2 * math.pi / max(total, 1)) * i
            x = int(radius * math.cos(angle))
            y = int(radius * math.sin(angle))

            group = node.get("group", "concept")
            is_book = group == "book"
            is_seed = group == "seed"
            is_hub = group == "hub"

            width = 240 if is_book else 170
            height = 85 if is_book else 60

            color_code = "6" if is_book else ("1" if is_seed else ("2" if is_hub else "5"))
            label_text = node.get("label", "")

            canvas_nodes.append({
                "id": str(node["id"]),
                "type": "text",
                "text": f"### 📖 [[{label_text}]]" if is_book else f"**[[{label_text}]]**",
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "color": color_code
            })

        for i, edge in enumerate(edges):
            canvas_edges.append({
                "id": f"edge_{i}",
                "fromNode": str(edge["from"]),
                "fromSide": "right",
                "toNode": str(edge["to"]),
                "toSide": "left"
            })

        return json.dumps({"nodes": canvas_nodes, "edges": canvas_edges}, ensure_ascii=False, indent=2)