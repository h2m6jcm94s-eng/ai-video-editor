# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.

import json

import pytest

from shared_py.verb_registry import VerbDefinition, VerbRegistry, make_default_registry


class TestVerbRegistry:
    def test_register_and_get(self):
        reg = VerbRegistry()
        reg.register(VerbDefinition(id="test_verb", category="edit", implemented=True))
        assert reg.get("test_verb") is not None
        assert reg.get("missing") is None

    def test_duplicate_raises(self):
        reg = VerbRegistry()
        reg.register(VerbDefinition(id="dup", category="edit"))
        with pytest.raises(ValueError):
            reg.register(VerbDefinition(id="dup", category="edit"))

    def test_default_registry_covers_implemented_verbs(self):
        reg = make_default_registry()
        # Command verbs
        assert reg.get("trim_slot").implemented is True
        assert reg.get("zoom_in").implemented is True
        assert reg.get("apply_filter").implemented is True
        # Effect verbs
        assert reg.get("shake").implemented is True
        assert reg.get("world_text").implemented is True
        assert reg.get("world_text").prerequisites == ["depth"]
        # Ledger verbs
        assert reg.get("hard_cut").implemented is True
        assert reg.get("fade").ledger_ref == "fade"

    def test_json_export_roundtrip(self):
        reg = make_default_registry()
        data = json.loads(reg.to_json())
        assert len(data) == len(reg.list_all())
        assert data[0]["id"] == reg.list_all()[0].id

    def test_markdown_contains_table(self):
        reg = make_default_registry()
        md = reg.to_markdown()
        assert "# Verb Registry" in md
        assert "`trim_slot`" in md
        assert "`world_text`" in md
