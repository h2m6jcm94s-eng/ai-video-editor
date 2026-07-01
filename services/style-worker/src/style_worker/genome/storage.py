# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Simple JSON persistence helpers for Style Genome fingerprints.

The storage-backed helpers (:func:`save_genome` and :func:`load_genome`) use the
shared storage abstraction so genomes can live on local disk or R2 without
caller changes. Legacy :func:`save_genome_json` / :func:`load_genome_json` remain
for direct filesystem use (mostly tests).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Union

from shared_py.models import StyleGenome
from shared_py.storage import get_storage


def save_genome_json(genome: Union[StyleGenome, dict], output_path: str) -> None:
    """Write a Style Genome to disk as pretty-printed JSON."""
    if isinstance(genome, StyleGenome):
        data = genome.model_dump(by_alias=True)
    else:
        data = dict(genome)

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_genome_json(path: str) -> dict:
    """Load a Style Genome from a JSON file."""
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def save_genome(user_id: str, genome_id: str, genome: Union[StyleGenome, dict]) -> str:
    """Persist a Style Genome to storage at ``genomes/{user_id}/{genome_id}.pb``.

    The payload is JSON for now; the ``.pb`` extension preserves the key layout
    expected by the rest of the system.
    """
    if isinstance(genome, StyleGenome):
        data = genome.model_dump(by_alias=True)
    else:
        data = dict(genome)

    payload = json.dumps(data, indent=2).encode("utf-8")
    key = f"genomes/{user_id}/{genome_id}.pb"
    get_storage().put(payload, key, content_type="application/json")
    return key


def load_genome(user_id: str, genome_id: str) -> dict:
    """Load a Style Genome from storage at ``genomes/{user_id}/{genome_id}.pb``."""
    key = f"genomes/{user_id}/{genome_id}.pb"
    ext = ".pb"

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        local_path = tmp.name
    try:
        get_storage().get(key, local_path)
        with Path(local_path).open("r", encoding="utf-8") as f:
            return json.load(f)
    finally:
        try:
            Path(local_path).unlink(missing_ok=True)
        except OSError:
            pass
