# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Thin wrapper around the Twelve Labs Embed API v2 (Marengo 3.0)."""

import os
import time
from typing import List, Optional

import numpy as np

from shared_py.logging_config import StructuredLogger

logger = StructuredLogger("reason_worker.marengo_client")


class MarengoClient:
    """Client for Twelve Labs Marengo 3.0 multimodal embeddings.

    The wrapper is defensive: if the SDK is missing or the API key is not
    configured, ``available()`` returns ``False`` and all embedding methods
    return ``None``.  This lets the pipeline fall back to heuristic scoring
    when Marengo is not wired up.
    """

    DEFAULT_MODEL = "marengo3.0"

    def __init__(self, api_key: Optional[str] = None, model_name: str = DEFAULT_MODEL):
        self.api_key = api_key or os.environ.get("TWELVELABS_API_KEY")
        self.model_name = model_name
        self._client = None
        self._import_error: Optional[str] = None
        self._ensure_client()

    def _ensure_client(self) -> None:
        try:
            from twelvelabs import TwelveLabs  # type: ignore[import-not-found]

            if not self.api_key:
                raise RuntimeError("TWELVELABS_API_KEY not configured")
            self._client = TwelveLabs(api_key=self.api_key)
        except Exception as e:  # pragma: no cover - import/env failures
            self._import_error = str(e)
            logger.warning("Twelve Labs SDK unavailable", error=str(e))

    def available(self) -> bool:
        return self._client is not None

    def embed_text(self, text: str) -> Optional[np.ndarray]:
        """Return a Marengo text embedding or ``None`` on failure."""
        if not self.available():
            return None
        try:
            from twelvelabs import TextInputRequest  # type: ignore[import-not-found]

            resp = self._client.embed.v_2.create(
                input_type="text",
                model_name=self.model_name,
                text=TextInputRequest(input_text=text),
            )
            if resp.data:
                return np.array(resp.data[0].embedding, dtype=np.float32)
        except Exception as e:
            logger.warning("Twelve Labs text embedding failed", error=str(e))
        return None

    def embed_video_file(
        self,
        file_path: str,
        embedding_option: Optional[List[str]] = None,
        embedding_scope: Optional[List[str]] = None,
    ) -> Optional[np.ndarray]:
        """Upload a local video and return a fused asset-level embedding.

        For short videos (the typical user clip), the synchronous API returns
        embeddings immediately.  Longer videos fall back to async polling.
        """
        if not self.available():
            return None

        embedding_option = embedding_option or ["visual", "audio"]
        embedding_scope = embedding_scope or ["asset"]

        try:
            from twelvelabs import (  # type: ignore[import-not-found]
                MediaSource,
                VideoInputRequest,
            )

            with open(file_path, "rb") as f:
                asset = self._client.assets.create(method="direct", file=f)

            # Wait for the uploaded asset to become ready.
            while True:
                asset = self._client.assets.retrieve(asset.id)
                if asset.status == "ready":
                    break
                if asset.status == "failed":
                    raise RuntimeError(f"Asset processing failed: {asset.id}")
                time.sleep(2)

            video_input = VideoInputRequest(
                media_source=MediaSource(asset_id=asset.id),
                embedding_option=embedding_option,
                embedding_scope=embedding_scope,
                embedding_type=["fused_embedding"],
            )

            # Try sync first (videos under ~10 minutes).
            try:
                resp = self._client.embed.v_2.create(
                    input_type="video",
                    model_name=self.model_name,
                    video=video_input,
                )
            except Exception:
                # Fall back to async for longer videos.
                resp = self._poll_video_embedding_task(video_input)

            if not resp or not resp.data:
                return None

            # Prefer fused asset embedding; fall back to the first available.
            for emb in resp.data:
                if emb.embedding_scope in embedding_scope and emb.embedding_option == "fused":
                    return np.array(emb.embedding, dtype=np.float32)
            return np.array(resp.data[0].embedding, dtype=np.float32)
        except Exception as e:
            logger.warning("Twelve Labs video embedding failed", error=str(e))
        return None

    def _poll_video_embedding_task(self, video_input) -> Optional[object]:
        """Create and poll an async embedding task for long videos."""
        try:
            task = self._client.embed.v_2.tasks.create(
                input_type="video",
                model_name=self.model_name,
                video=video_input,
            )
            while True:
                task = self._client.embed.v_2.tasks.retrieve(task_id=task.id)
                if task.status == "ready":
                    return task
                if task.status == "failed":
                    raise RuntimeError(f"Embedding task failed: {task.id}")
                time.sleep(5)
        except Exception as e:
            logger.warning("Twelve Labs async video embedding failed", error=str(e))
        return None
