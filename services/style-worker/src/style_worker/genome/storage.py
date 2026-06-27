# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Simple JSON persistence helpers for Style Genome fingerprints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Union

from shared_py.models import StyleGenome


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
