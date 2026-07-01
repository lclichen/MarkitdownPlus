"""
fast_api_v2.py
==============
FastAPI service for document-to-Markdown conversion.

Reference: MinerU's fast_api.py architecture.
    Sync endpoint:  POST /file_parse
    Async endpoint: POST /tasks + GET /tasks/{id} + GET /tasks/{id}/result
    Health:         GET /health

Port: 8000 (configurable via config.json or environment variables)

Concurrency:
    A single HybridConverter instance is shared (singleton).
    The MarkItDown path modifies converter instances via
    find_and_wrap_ocr_services, so a threading.Lock serializes
    all conversions to prevent hook conflicts.

Usage:
    python fast_api_v2.py
    uvicorn fast_api_v2:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import os
import shutil
import threading
import time
import uuid
import zipfile
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import uvicorn
from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel

from converter_core import (
    HybridConverter,
    get_converter,
    SUPPORTED_SUFFIXES,
)
from image_hook import package_output

# Configuration loader
from config_loader import (
    get_api_host,
    get_api_port,
    get_task_retention_seconds,
    get_task_cleanup_interval,
    get_sync_timeout,
    get_upload_dir,
    get_output_dir,
    get_config,
)


# ============================================================
# Task Status Constants
# ============================================================

TASK_PENDING = "pending"
TASK_PROCESSING = "processing"
TASK_COMPLETED = "completed"
TASK_FAILED = "failed"

# Image convert modes and response formats (from config)
IMAGE_CONVERT_MODES = ["OCR", "Caption", "Origin"]
RESPONSE_FORMATS = ["json", "zip"]


# ============================================================
# Conversion Lock
# ============================================================

_conversion_lock = threading.Lock()


# ============================================================
# Task Model
# ============================================================

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ConvertTask:
    """Represents a single conversion task."""
    task_id: str
    file_name: str
    image_convert_mode: str
    response_format: str
    status: str = TASK_PENDING
    created_at: str = field(default_factory=utc_now_iso)
    completed_at: str | None = None
    md_content: str = ""
    images: dict[str, str] = field(default_factory=dict)
    image_count: int = 0
    output_zip_path: str | None = None
    error: str | None = None
    _upload_path: str = ""
    _output_dir: str = ""

    def to_status_payload(self) -> dict:
        """Status info (no content)."""
        return {
            "task_id": self.task_id,
            "status": self.status,
            "file_name": self.file_name,
            "image_convert_mode": self.image_convert_mode,
            "response_format": self.response_format,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "image_count": self.image_count,
            "error": self.error,
        }


# ============================================================
# Async Task Manager
# ============================================================

class AsyncTaskManager:
    """
    Manages async conversion tasks.

    - Tasks are stored in-memory (dict)
    - Conversion runs in asyncio.to_thread (sync HybridConverter)
    - A global threading.Lock serializes the actual conversion
    - Expired tasks are cleaned up periodically
    """

    def __init__(
        self,
        retention_seconds: int | None = None,
        cleanup_interval: int | None = None,
    ):
        config = get_config()
        self.tasks: dict[str, ConvertTask] = {}
        self.retention_seconds = retention_seconds or get_task_retention_seconds()
        self.cleanup_interval = cleanup_interval or get_task_cleanup_interval()
        self._cleanup_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def start(self):
        """Start the background cleanup loop."""
        if self.retention_seconds > 0 and self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            print(f"[TaskManager] Cleanup loop started "
                  f"(retention={self.retention_seconds}s, "
                  f"interval={self.cleanup_interval}s)")

    async def stop(self):
        """Stop the background cleanup loop."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
        print("[TaskManager] S
