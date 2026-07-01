"""
image_hook.py
=============
Hook into MarkItDown's internal OCR service via instance-level proxy.

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │  find_and_wrap_ocr_services(md_converter, registry, mode)   │
    │                                                             │
    │  for each ConverterRegistration in md_converter._converters:│
    │    └── scan converter instance __dict__ for OCR service     │
    │    └── replace with HookedOCRService proxy                  │
    │    └── save (converter, attr_name, original) for restore    │
    │                                                             │
    │  returns restore() callable                                 │
    └─────────────────────────────────────────────────────────────┘

    During MarkItDown.convert():
    ┌──────────────────────────────────────────────────┐
    │  PdfConverterWithOCR.convert()                   │
    │    └── self._ocr_service.extract_text(stream)    │
    │        ← PROXY: capture image → registry         │
    │        ← mode-aware prompt selection             │
    │        ← Origin: skip VLM, return ![image](...)  │
    │        ← OCR/Caption: call original VLM          │
    └──────────────────────────────────────────────────┘

    After conversion:
        restore() — unwrap all proxies
        post_process_markdown_images() — safety net for residual base64
        package_output() — ZIP (md + images/) or plain .md

Image Naming: {source_stem}_{source_type}_{page_label}_img{seq:03d}.{ext}
    e.g. annual_report_xlsx_sheet1_img001.png
         report_pdf_p3_img002.png
         notes_docx_img001.jpg
"""

from __future__ import annotations

import base64
import inspect
import io
import os
import re
import tempfile
import zipfile
from dataclasses import dataclass
from typing import Any, Callable


# ============================================================
# Helpers
# ============================================================

def sanitize_for_filename(text: str) -> str:
    """Sanitize text for safe use in filenames."""
    if not text:
        return ""
    text = re.sub(r'[^\w\-]', '_', text)
    text = re.sub(r'_+', '_', text)
    return text.strip('_').lower()


def parse_data_uri(data_uri: str) -> tuple[str, str]:
    """
    Parse a data URI into (mime_type, b64_data).
    Input:  "data:image/png;base64,iVBORw0KG..."
    Output: ("image/png", "iVBORw0KG...")
    """
    match = re.match(
        r'data:(image/[a-zA-Z0-9.+-]+);base64,(.+)',
        data_uri,
        re.DOTALL,
    )
    if match:
        return match.group(1), match.group(2).strip()
    return "image/png", data_uri


def mime_to_ext(mime_type: str) -> str:
    """Convert MIME type to file extension."""
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/bmp": ".bmp",
        "image/tiff": ".tiff",
    }.get(mime_type, ".png")


# ============================================================
# 1. Image Entry & Registry
# ============================================================

@dataclass
class ImageEntry:
    """A single extracted image with full provenance metadata."""
    image_id: str               # internal ID: "img_0001"
    source_stem: str            # source filename without ext: "annual_report"
    source_type: str            # source file type: "pdf", "xlsx", "docx"
    page_label: str             # page/sheet identifier: "p3", "sheet1", ""
    seq: int                    # global sequence number
    b64_data: str               # base64 encoded (no data: prefix)
    mime_type: str = "image/png"
    alt_text: str = ""          # OCR text or VLM caption
    processing_mode: str = ""   # "OCR", "Caption", "Origin"
    origin: str = ""            # "hook", "postprocess", "xlsx_table", "xlsx_standalone"

    @property
    def ext(self) -> str:
        return mime_to_ext(self.mime_type)

    @property
    def filename(self) -> str:
        """Filename following the naming convention."""
        parts = [self.source_stem, self.source_type]
        if self.page_label:
            parts.append(self.page_label)
        parts.append(f"img{self.seq:03d}")
        return "_".join(parts) + self.ext

    @property
    def data_uri(self) -> str:
        return f"data:{self.mime_type};base64,{self.b64_data}"

    @property
    def byte_size(self) -> int:
        return len(base64.b64decode(self.b64_data))

    def __repr__(self):
        return f"<ImageEntry {self.filename} ({self.byte_size}B, {self.processing_mode})>"


class ImageRegistry:
    """
    Collects all images encountered during document processing.
    Single source of truth for image packaging.
    """

    def __init__(self, source_stem: str = "", source_type: str = ""):
        self.source_stem = sanitize_for_filename(source_stem) or "document"
        self.source_type = sanitize_for_filename(source_type) or "unknown"
        self._images: list[ImageEntry] = []
        self._counter = 0

    def register(
        self,
      
