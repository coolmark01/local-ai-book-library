# -*- coding: utf-8 -*-
"""
PDF 文字提取模組（支援自動檢測 + OCR + 品質檢查）
============================================
功能：
  1. 自動檢測 PDF 是否為「文字型」或「掃描影像型」
  2. 文字型 PDF → 直接提取內嵌文字
  3. 掃描型 PDF → 自動執行 OCR 文字辨識
  4. 支援多 OCR 引擎後援（pytesseract → paddleocr）
  5. OCR 品質檢查：自動評估辨識結果的可靠度

使用方式：
  基本用法（回傳純文字，向後相容）：
      from pdf_text_extractor import extract_pdf_text
      pdf_text = extract_pdf_text(pdf_path)

  完整用法（回傳文字 + 品質報告）：
      from pdf_text_extractor import extract_pdf_text_with_quality
      pdf_text, quality = extract_pdf_text_with_quality(pdf_path)
      if quality["pass"]:
          # 品質足夠，正常使用
      else:
          # 品質過低，警告使用者

  單獨品質檢查：
      from pdf_text_extractor import assess_ocr_quality
      quality = assess_ocr_quality(text, total_pages)
"""

import os
import re
import logging
from typing import Optional, Tuple, Dict, Any
from collections import Counter

logger = logging.getLogger(__name__)

# ===================================================================
# 品質檢查函數
# ===================================================================

def assess_ocr_quality(text: str, total_pages: int) -> Dict[str, Any]:
    """
    評估 OCR 結果的品質，回傳評分與建議。

    評分項目（滿分 100）：
        - 字元密度（30 分）：每頁至少要有多少字元才算有效
        - 中文字元比例（30 分）：有效中文文本的中文字元比例應 > 60%
        - 重複字元率（20 分）：最常見字元不應異常高
        - 連續重複模式（20 分）：連續 3 個以上相同字元可能代表問題

    參數：
        text:          OCR 辨識後的文字字串
        total_pages:   PDF 總頁數

    回傳：
        dict: {
            "score":    int,    # 品質分數（0~100）
            "pass":     bool,   # 是否通過品質閾值
            "level":    str,    # "good" / "fair" / "poor" / "empty"
            "details":  dict,   # 各項目細項
            "warning":  str,    # 警告訊息（若有）
        }
    """
    if not text or not text.strip():
        return {
            "score": 0,
            "pass": False,
            "level": "empty",
            "details": {},
            "warning": "OCR 結果為空，完全沒有辨識到文字",
        }

    clean_text = text.strip()
    total_chars = len(clean_text)
    chars_per_page = total_chars / max(total_pages, 1)

    # 1. 字元密度評分（0~30 分）
    if chars_per_page >= 50:
        density_score = 30
    elif chars_per_page >= 20:
        density_score = 15
    elif chars_per_page >= 5:
        density_score = 5
    else:
        density_score = 0

    # 2. 中文字元比例（0~30 分）
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]', clean_text))
    all_alpha_chars = len(re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf\w]', clean_text))
    chinese_ratio = chinese_chars / max(all_alpha_chars, 1)

    if chinese_ratio >= 0.6:
        chinese_score = 30
    elif chinese_ratio >= 0.3:
        chinese_score = 15
    elif chinese_ratio >= 0.1:
        chinese_score = 5
    else:
        chinese_score = 0

    # 3. 重複字元率（0~20 分）
    no_space = re.sub(r'\s', '', clean_text)
    if len(no_space) > 0:
        freq = Counter(no_space)
        top3_sum = sum(v for _, v in freq.most_common(3))
        top3_ratio = top3_sum / len(no_space)
    else:
        top3_ratio = 0

    if top3_ratio <= 0.15:
        freq_score = 20
    elif top3_ratio <= 0.25:
        freq_score = 10
    elif top3_ratio <= 0.40:
        freq_score = 5
    else:
        freq_score = 0

    # 4. 連續重複模式（0~20 分）
    repeated_pattern = re.findall(r'(.)\1{2,}', clean_text)
    repeated_text = ''.join(repeated_pattern)
    repeated_ratio = len(repeated_text) / max(total_chars, 1)

    if repeated_ratio <= 0.02:
        repeat_score = 20
    elif repeated_ratio <= 0.05:
        repeat_score = 10
    elif repeated_ratio <= 0.10:
        repeat_score = 5
    else:
        repeat_score = 0

    # 總分計算
    total_score = density_score + chinese_score + freq_score + repeat_score

    # 判定結果
    if total_score >= 60 and chars_per_page >= 30:
        level = "good"
        pass_ok = True
        warning = ""
    elif total_score >= 40 and chars_per_page >= 15:
        level = "fair"
        pass_ok = True
        warning = "OCR 品質中等，部分內容可能辨識不精確，建議事後抽查"
    elif total_score >= 20:
        level = "poor"
        pass_ok = False
        warning = "OCR 品質過低，辨識結果可能充滿錯字或亂碼，建議重新掃描或手動處理"
    else:
        level = "empty"
        pass_ok = False
        warning = "OCR 結果幾乎無效，無法用於知識庫"

    return {
        "score": total_score,
        "pass": pass_ok,
        "level": level,
        "details": {
            "chars_per_page": round(chars_per_page, 1),
            "total_chars": total_chars,
            "chinese_ratio": round(chinese_ratio, 2),
            "top3_freq_ratio": round(top3_ratio, 2),
            "repeated_ratio": round(repeated_ratio, 4),
            "density_score": density_score,
            "chinese_score": chinese_score,
            "freq_score": freq_score,
            "repeat_score": repeat_score,
        },
        "warning": warning,
    }


# ===================================================================
# 主要入口函數（回傳純文字，向後相容）
# ===================================================================

def extract_pdf_text(pdf_path: str, min_text_length: int = 50) -> Optional[str]:
    """
    自動檢測 PDF 類型並提取文字（向後相容版本，僅回傳文字）。

    參數：
        pdf_path:       PDF 檔案路徑
        min_text_length: 判定為「有文字」的最小字元數，預設 50
                         若 PDF 提取的文字少於此值，會自動切換到 OCR

    回傳：
        提取的文字字串，若無法提取則回傳 None
    """
    text, _ = extract_pdf_text_with_quality(pdf_path, min_text_length)
    return text


# ===================================================================
# 主要入口函數（回傳文字 + 品質報告）
# ===================================================================

def extract_pdf_text_with_quality(
    pdf_path: str,
    min_text_length: int = 50
) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    自動檢測 PDF 類型並提取文字，同時回傳 OCR 品質報告。

    參數：
        pdf_path:       PDF 檔案路徑
        min_text_length: 判定為「有文字」的最小字元數，預設 50

    回傳：
        tuple: (text: Optional[str], quality: dict)
            - text:       提取的文字字串，若無法提取則為 None
            - quality:    品質報告 dict（含 score, pass, level, details, warning）
    """
    if not os.path.exists(pdf_path):
        logger.error(f"[PDF] 檔案不存在: {pdf_path}")
        return None, {"score": 0, "pass": False, "level": "empty", "warning": "檔案不存在"}

    try:
        import fitz  # pymupdf
    except ImportError:
        logger.error("[PDF] 需要安裝 pymupdf: pip install pymupdf")
        return None, {"score": 0, "pass": False, "level": "empty", "warning": "pymupdf 未安裝"}

    doc = None
    try:
        doc = fitz.open(pdf_path)
        total_text = ""
        page_count = len(doc)

        # 逐頁提取文字
        for page_num in range(page_count):
            page = doc[page_num]
            text = page.get_text("text").strip()
            if text:
                total_text += f"\n--- 第 {page_num + 1} 頁 ---\n{text}"

        doc.close()
        doc = None

        # 判斷是否有足夠的文字
        clean_text = total_text.strip()
        if len(clean_text) >= min_text_length:
            logger.info(
                f"[PDF] 文字型 PDF，共 {page_count} 頁，"
                f"提取文字 {len(clean_text)} 字元"
            )
            quality = assess_ocr_quality(clean_text, page_count)
            if not quality["pass"]:
                logger.warning(
                    f"[PDF] 文字型 PDF 但品質偏低 ({quality['level']}, "
                    f"分數 {quality['score']}/100): {quality.get('warning', '')}"
                )
            return clean_text, quality

        # 文字不足，判定為掃描型 PDF，執行 OCR
        logger.warning(
            f"[PDF] 文字量不足 ({len(clean_text)} 字元 < {min_text_length})，"
            f"判定為掃描型 PDF，開始執行 OCR..."
        )
        ocr_result = _ocr_scanned_pdf(pdf_path, page_count)

        if ocr_result:
            quality = assess_ocr_quality(ocr_result, page_count)
            logger.info(
                f"[PDF] OCR 完成，品質評分: {quality['score']}/100 "
                f"({quality['level']})"
            )
            if not quality["pass"]:
                logger.warning(
                    f"[PDF] OCR 品質過低 ({quality['level']}, "
                    f"分數 {quality['score']}/100): {quality.get('warning', '')}"
                )
            return ocr_result, quality
        else:
            logger.error(f"[PDF] OCR 執行失敗，無法提取文字")
            return None, {"score": 0, "pass": False, "level": "empty",
                         "warning": "OCR 執行失敗"}

    except Exception as e:
        logger.error(f"[PDF] 提取文字時發生錯誤: {e}", exc_info=True)
        if doc is not None:
            doc.close()
        return None, {"score": 0, "pass": False, "level": "empty",
                     "warning": f"提取異常: {str(e)}"}


# ===================================================================
# OCR 掃描型 PDF 處理
# ===================================================================

def _ocr_scanned_pdf(pdf_path: str, page_count: int) -> Optional[str]:
    """
    對掃描型 PDF 執行 OCR 文字辨識。
    優先使用 pytesseract，若不可用則嘗試 paddleocr。
    """
    # 嘗試 pytesseract
    try:
        return _ocr_with_tesseract(pdf_path, page_count)
    except Exception as e:
        logger.warning(f"[OCR] pytesseract 失敗: {e}，嘗試 paddleocr...")

    # 後援：paddleocr
    try:
        return _ocr_with_paddleocr(pdf_path, page_count)
    except Exception as e:
        logger.error(f"[OCR] 所有 OCR 引擎均失敗: {e}")
        logger.error(
            "[OCR] 請安裝以下任一 OCR 引擎：\n"
            "  選項A（推薦）: pip install paddlepaddle paddleocr\n"
            "  選項B: pip install pytesseract\n"
            "         並安裝 Tesseract OCR Engine: "
            "https://github.com/tesseract-ocr/tesseract/wiki"
        )
        return None


# ===================================================================
# 引擎 A：pytesseract
# ===================================================================

def _ocr_with_tesseract(pdf_path: str, page_count: int) -> str:
    """使用 pytesseract 對掃描型 PDF 逐頁 OCR"""
    import fitz  # pymupdf
    import pytesseract
    from PIL import Image
    import io

    doc = fitz.open(pdf_path)
    ocr_text_parts = []
    dpi = 300  # OCR 解析度，越高越精確但越慢

    for page_num in range(len(doc)):
        page = doc[page_num]
        # 將 PDF 頁面轉為高解析度圖片
        pix = page.get_pixmap(dpi=dpi)
        img_data = pix.tobytes("png")
        image = Image.open(io.BytesIO(img_data))

        # 執行 OCR（繁體中文）
        try:
            text = pytesseract.image_to_string(image, lang='chi_tra')
        except pytesseract.TesseractNotFoundError:
            # 嘗試簡體中文
            try:
                text = pytesseract.image_to_string(image, lang='chi_sim')
            except pytesseract.TesseractNotFoundError:
                # 嘗試英文
                text = pytesseract.image_to_string(image, lang='eng')

        text = text.strip()
        if text:
            ocr_text_parts.append(f"--- 第 {page_num + 1} 頁 ---\n{text}")
            if (page_num + 1) % 20 == 0:
                logger.info(f"[OCR] pytesseract 進度: {page_num + 1}/{len(doc)} 頁")

        # 每處理完一頁就釋放記憶體
        del image
        del pix

    doc.close()

    result = "\n".join(ocr_text_parts)
    logger.info(
        f"[OCR] pytesseract 完成，共 {len(ocr_text_parts)} 頁有文字，"
        f"總計 {len(result)} 字元"
    )
    return result


# ===================================================================
# 引擎 B：paddleocr
# ===================================================================

def _ocr_with_paddleocr(pdf_path: str, page_count: int) -> str:
    """使用 paddleocr 對掃描型 PDF 逐頁 OCR（對中文支援更好）"""
    from paddleocr import PaddleOCR
    import fitz  # pymupdf

    # 初始化 OCR 引擎（use_angle_cls=True 支援角度辨識）
    logger.info("[OCR] 正在初始化 PaddleOCR（首次執行會下載模型，請稍候）...")
    ocr = PaddleOCR(use_angle_cls=True, lang='ch', show_log=False)
    doc = fitz.open(pdf_path)

    ocr_text_parts = []
    dpi = 300

    for page_num in range(len(doc)):
        page = doc[page_num]
        pix = page.get_pixmap(dpi=dpi)
        img_data = pix.tobytes("png")

        # 執行 OCR
        result = ocr.ocr(img_data, cls=True)

        # 提取文字
        page_text = ""
        if result and result[0]:
            for line in result[0]:
                if line and len(line) >= 2:
                    page_text += line[1][0] + "\n"

        page_text = page_text.strip()
        if page_text:
            ocr_text_parts.append(f"--- 第 {page_num + 1} 頁 ---\n{page_text}")

        if (page_num + 1) % 20 == 0:
            logger.info(f"[OCR] PaddleOCR 進度: {page_num + 1}/{len(doc)} 頁")

    doc.close()

    result = "\n".join(ocr_text_parts)
    logger.info(
        f"[OCR] PaddleOCR 完成，共 {len(ocr_text_parts)} 頁有文字，"
        f"總計 {len(result)} 字元"
    )
    return result


# ===================================================================
# 輔助函數：批量檢查多個 PDF
# ===================================================================

def check_pdf_types(pdf_paths: list) -> dict:
    """
    批量檢查多個 PDF 的類型（文字型 / 掃描型）及品質。

    回傳：
        dict: {
            pdf_path: {
                "type": "text"/"scanned"/"error",
                "text_length": int,
                "pages": int,
                "is_scanned": bool,
                "quality": {  # 若有文字則包含品質報告
                    "score": int,
                    "pass": bool,
                    "level": str,
                    "warning": str,
                }
            }
        }
    """
    import fitz
    results = {}
    for pdf_path in pdf_paths:
        try:
            doc = fitz.open(pdf_path)
            total_text = ""
            for page in doc:
                total_text += page.get_text("text")
            doc.close()

            text_len = len(total_text.strip())
            is_scanned = text_len < 50

            entry = {
                "type": "scanned" if is_scanned else "text",
                "text_length": text_len,
                "pages": len(doc),
                "is_scanned": is_scanned,
            }

            # 若有足夠文字，進行品質評估
            if text_len >= 50:
                quality = assess_ocr_quality(total_text.strip(), len(doc))
                entry["quality"] = {
                    "score": quality["score"],
                    "pass": quality["pass"],
                    "level": quality["level"],
                    "warning": quality["warning"],
                }

            results[pdf_path] = entry
        except Exception as e:
            results[pdf_path] = {
                "type": "error",
                "error": str(e),
            }
    return results


# ===================================================================
# 輔助函數：將掃描型 PDF 預處理為文字型 PDF（使用 OCRmypdf）
# ===================================================================

def preprocess_pdf_with_ocrmypdf(input_pdf: str, output_pdf: str) -> bool:
    """
    使用 ocrmypdf 工具將掃描型 PDF 轉為文字型 PDF。
    這比在程式中逐頁 OCR 更快，因為它使用多執行緒。

    需要：pip install ocrmypdf
    並需系統安裝 Tesseract OCR Engine。

    回傳：
        True 表示成功，False 表示失敗
    """
    try:
        import ocrmypdf
        ocrmypdf.ocr(
            input_pdf,
            output_pdf,
            language='chi_tra',       # 繁體中文
            output_type='pdf',
            skip_big=15,              # 跳過大於 15MB 的頁面（避免卡住）
            progress_bar=False,
        )
        logger.info(f"[OCR] ocrmypdf 完成: {input_pdf} -> {output_pdf}")
        return True
    except ImportError:
        logger.error("[OCR] 需要安裝 ocrmypdf: pip install ocrmypdf")
        return False
    except Exception as e:
        logger.error(f"[OCR] ocrmypdf 執行失敗: {e}")
        return False


# ===================================================================
# 主程式測試用
# ===================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python pdf_text_extractor.py <pdf路徑>")
        print("範例: python pdf_text_extractor.py 超級記憶潜能开发.pdf")
        sys.exit(1)

    pdf_path = sys.argv[1]

    # 配置日誌
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
    )

    print(f"\n正在處理: {pdf_path}")
    print("-" * 60)

    # 執行提取（含品質檢查）
    text, quality = extract_pdf_text_with_quality(pdf_path)

    if text:
        print(f"\n✅ 成功提取文字，共 {len(text)} 字元")
        print(f"📊 品質評分: {quality['score']}/100 ({quality['level']})")
        if quality.get('warning'):
            print(f"⚠️  警告: {quality['warning']}")
        print("-" * 60)
        print("前 500 字：")
        print(text[:500])
    else:
        print(f"\n❌ 無法提取文字")
        print(f"📊 品質評分: {quality['score']}/100 ({quality['level']})")
        if quality.get('warning'):
            print(f"⚠️  原因: {quality['warning']}")
        print("   建議安裝 PaddleOCR 或 Tesseract 後重試")
