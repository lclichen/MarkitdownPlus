"""
converter_core.py
=================
Shared conversion logic for MarkItDown WebUI and FastAPI service.

Extracted from markitdown_webui_v2.py — contains all conversion
logic without Gradio dependencies.

Both markitdown_webui_v2.py and fast_api.py import from this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from bs4 import BeautifulSoup, NavigableString, Tag
from openai import OpenAI
from markitdown import MarkItDown

# Image hook infrastructure
from image_hook import (
    ImageRegistry,
    find_and_wrap_ocr_services,
    post_process_markdown_images,
    package_output,
    parse_data_uri,
    sanitize_for_filename,
)

# Rewrite Xlsx Converter (custom mineru xlsx processor)
from mineru.model.xlsx.xlsx_converter import XlsxConverter

# Configuration loader
from config_loader import get_config, get_supported_formats


# ============================================================
# Constants
# ============================================================

SUPPORTED_SUFFIXES = get_supported_formats()


# ============================================================
# OCR Result
# ============================================================

@dataclass
class OCRResult:
    """Result from OCR extraction."""
    text: str
    confidence: float | None = None
    backend_used: str | None = None
    error: str | None = None


# ============================================================
# XLSX Conversion Helpers
# ============================================================

def convert_path(file_path: str):
    """Convert xlsx file by path into page structures."""
    with open(file_path, "rb") as fh:
        return convert_binary(fh)


def convert_binary(file_binary: BinaryIO):
    """Convert xlsx binary stream into page structures."""
    converter = XlsxConverter()
    converter.convert(file_binary)
    return converter.pages


def convert_element_to_markdown(
    element,
    image_convert_mode: str,
    ocr_service: "LLMVisionOCRService",
    registry: ImageRegistry | None = None,
    source_stem: str = "",
    source_type: str = "",
    page_label: str = "",
) -> str:
    """
    Recursively convert HTML element to Markdown.
    Supports: strong, em, s, a, img, eq (custom formula tag).

    When registry is provided, images are registered into it.
    """
    if isinstance(element, NavigableString):
        text = str(element)
        text = text.replace('\xa0', ' ')
        return text

    if not isinstance(element, Tag):
        return ""

    tag_name = element.name.lower()

    # 1. Formula <eq>
    if tag_name == 'eq':
        latex_content = element.get_text(strip=True)
        return f" ${latex_content}$ "

    # 2. Image <img>
    if tag_name == 'img':
        src = element.get('src', '')
        alt = element.get('alt', 'image')
        if src:
            if image_convert_mode == "OCR":
                ocr_text = ocr_service.extract_text(src).text.strip()
                if registry:
                    mime_type, b64_data = parse_data_uri(src)
                    entry = registry.register(
                        b64_data=b64_data,
                        mime_type=mime_type,
                        page_label=page_label,
                        alt_text=ocr_text,
                        processing_mode="OCR",
                        origin="xlsx_table",
                    )
                    return f"<!-- img: images/{entry.filename} -->\n*[Image OCR]\n{ocr_text}\n[End OCR]*"
                return f"*[Image OCR]\n{ocr_text}\n[End OCR]*"
            elif image_convert_mode == "Caption":
                ocr_caption = ocr_service.extract_caption(src).text.strip()
                if registry:
                    mime_type, b64_data = parse_data_uri(src)
                    entry = registry.register(
                        b64_data=b64_data,
                        mime_type=mime_type,
                        page_label=page_label,
                        alt_text=ocr_caption,
                        processing_mode="Caption",
                        origin="xlsx_table",
                    )
                    return f"<!-- img: images/{entry.filename} -->\n*[Image Caption]\n{ocr_caption}\n[End Caption]*"
                return f"*[Image Caption]\n{ocr_caption}\n[End Caption]*"
            elif image_convert_mode == "Origin":
                if registry:
                    mime_type, b64_data = parse_data_uri(src)
                    entry = registry.register(
                        b64_data=b64_data,
                        mime_type=mime_type,
                        page_label=page_label,
                        processing_mode="Origin",
                        origin="xlsx_table",
                    )
                    return f"![{alt}](images/{entry.filename})"
                return f"![{alt}]({src})"
            else:
                return f"![{alt}]({src})"
        return ""

    # 3. Hyperlink <a>
    if tag_name == 'a':
        href = element.get('href', '#')
        inner_text = "".join(
      
