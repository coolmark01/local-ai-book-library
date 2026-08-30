# -*- coding: utf-8 -*-
"""
文字處理模組 (text_processor.py)
================================
負責：HTML 結構清洗、PDF 格式修復與頁碼防誤殺過濾、簡繁轉換、停用詞表管理。
"""

import re
import logging
from typing import Set
from bs4 import BeautifulSoup

logger = logging.getLogger("LibraryLogger")

try:
    import opencc
    _converter = opencc.OpenCC('s2t')
    _HAS_OPENCC = True
except ImportError:
    _converter = None
    _HAS_OPENCC = False


def convert_to_traditional(text: str, enable: bool = True) -> str:
    """將簡體文字轉換為繁體。若未啟用或未安裝 opencc 則原樣返回。"""
    if not enable or not _HAS_OPENCC or not text:
        return text
    try:
        return _converter.convert(text)
    except Exception as e:
        logger.warning(f"[TextProcessor] 簡轉繁失敗: {e}")
        return text


def clean_html_content(html_content: str) -> str:
    """清洗 EPUB/HTML 內容，移除腳註、樣式與非正文標籤並保留排版文字。"""
    if not html_content:
        return ""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        # 移除干擾元素
        for tag in soup.find_all(['sup', 'sub', 'script', 'style', 'nav', 'header', 'footer']):
            tag.decompose()
        for tag in soup.find_all(class_=re.compile(r'(footnote|annotation|sidebar|pager)', re.I)):
            tag.decompose()

        text = soup.get_text(separator='\n')
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return '\n'.join(lines)
    except Exception as e:
        logger.warning(f"[TextProcessor] HTML 清洗失敗: {e}")
        return ""


def clean_pdf_text(text: str) -> str:
    """
    清洗 PDF 文字：
    1. 精確移除頁首/頁尾與頁碼標註，防止誤刪合法獨立數據
    2. 自動修復 PDF 斷行，維持語義連貫
    """
    if not text:
        return ""

    # 1. 移除顯式頁碼格式
    text = re.sub(r'(?m)^\s*(?:第\s*\d+\s*頁(?:\s*/\s*共\s*\d+\s*頁)?|\bPage\s+\d+(?:\s+of\s+\d+)?\b)\s*$', '', text)
    text = re.sub(r'(?m)^\s*[-—~～]\s*\d+\s*[-—~～]\s*$', '', text)

    lines = text.split('\n')
    cleaned_lines = []
    
    # 句末中英文標點集合
    cjk_end_punct = set("。！？；：…")
    en_end_punct = set(".!?;:")
    all_end_punct = cjk_end_punct | en_end_punct

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # 單獨數字防誤殺：僅當行長 <= 4、且不包含小數點或清單標記 (如 1. ) 時過濾純數字頁碼
        if re.match(r'^\d{1,4}$', stripped):
            continue

        if not cleaned_lines:
            cleaned_lines.append(stripped)
            continue

        prev_line = cleaned_lines[-1]
        
        # 判斷是否需要合併斷行（上一行未結束且當前行非標題/條列）
        is_prev_ended = prev_line[-1] in all_end_punct
        is_curr_list = bool(re.match(r'^(?:[0-9]+[\.\)]|[\(（][0-9]+[\)）]|[•\-\*\u2022])\s+', stripped))

        if not is_prev_ended and not is_curr_list:
            # 中文字符相連直接接續，英文字符間補空格
            if prev_line and stripped and ord(prev_line[-1]) < 128 and ord(stripped[0]) < 128:
                cleaned_lines[-1] = f"{prev_line} {stripped}"
            else:
                cleaned_lines[-1] = f"{prev_line}{stripped}"
        else:
            cleaned_lines.append(stripped)

    return "\n".join(cleaned_lines)


def get_stop_words() -> Set[str]:
    """獲取精簡高效的中文與英文停用詞集合。"""
    return {
        # 中文代詞與虛詞
        '我', '你', '他', '她', '它', '我們', '你們', '他們', '她們', '自己',
        '這', '那', '這些', '那些', '這個', '那個', '這裡', '那裡', '某',
        '誰', '什麼', '哪', '哪個', '哪些', '怎樣', '如何',
        '的', '了', '著', '過', '嗎', '呢', '吧', '啊', '哦', '嗯', '呀',
        '是', '在', '有', '不', '沒', '也', '都', '就', '才', '又', '再',
        '還', '已', '將', '會', '能', '可以', '該', '應', '必須',
        '和', '與', '及', '或', '而', '而且', '但', '但是', '卻', '則',
        '如果', '因為', '所以', '雖然', '然而', '不過', '因此',
        '把', '被', '讓', '給', '向', '從', '到', '對', '關於', '對於',
        '個', '位', '件', '條', '本', '篇', '次', '種',
        '之', '其', '此', '彼', '中', '上', '下', '前', '後', '裡', '外',
        # 英文常見停用詞
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'shall', 'should',
        'can', 'could', 'may', 'might', 'must', 'and', 'or', 'but', 'if', 'then',
        'else', 'when', 'at', 'from', 'by', 'on', 'off', 'for', 'in', 'out', 'over',
        'to', 'into', 'with', 'about', 'against', 'between', 'through', 'during',
        'before', 'after', 'above', 'below', 'this', 'that', 'these', 'those', 'it', 'its'
    }