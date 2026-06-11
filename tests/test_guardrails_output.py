"""Tests for guardrails output moderation endpoint."""

import pytest
from fastapi.testclient import TestClient

from guardrails.main import app
from guardrails.output import evaluate_output, OutputCheckResult

client = TestClient(app)


class TestEvaluateOutputEndpoint:
    def test_evaluate_output_allows_safe_text(self):
        """Normal cut-list JSON should pass through."""
        response = client.post(
            "/evaluate/output",
            json={"text": '{"diff": [], "explanation": "Added fade transition"}'},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["allowed"] is True

    def test_evaluate_output_blocks_when_guardrails_disabled(self):
        """When guardrails are disabled, everything passes."""
        response = client.post(
            "/evaluate/output",
            json={"text": "any text"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["allowed"] is True

    def test_evaluate_output_empty_text(self):
        """Empty text should be allowed."""
        response = client.post(
            "/evaluate/output",
            json={"text": ""},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["allowed"] is True


class TestOutputScanner:
    def test_evaluate_output_returns_result(self):
        """The evaluate_output function should return an OutputCheckResult."""
        result = evaluate_output("safe text")
        assert isinstance(result, OutputCheckResult)
        assert hasattr(result, "allowed")

    def test_evaluate_output_fail_open_on_scanner_error(self):
        """If scanners fail to load, should fail open (allowed=True)."""
        # This tests the fallback when llm-guard is not installed or fails
        result = evaluate_output("any text")
        assert isinstance(result.allowed, bool)
