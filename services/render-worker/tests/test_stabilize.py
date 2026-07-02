# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Unit tests for stabilization helpers."""

from render_worker.stabilize import stabilization_available, stabilization_filter


def test_stabilization_filter_deshake():
    f = stabilization_filter("deshake")
    assert "deshake" in f


def test_stabilization_filter_vidstab():
    f = stabilization_filter("vidstab")
    assert "vidstabdetect" in f


def test_stabilization_available_deshake():
    assert stabilization_available("deshake") is True
