"""Tests for the effect logging infrastructure."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from dialectical_framework.agents.agent_context import agent_scope, get_current_agent
from dialectical_framework.agents.execution_report import (
    Effect,
    ExecutionReport,
    NodeRef,
)
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.utils.effect_logger import EffectLogger


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


@pytest.fixture
def log_dir(tmp_path: Path) -> Path:
    return tmp_path / "effect_logs"


@pytest.fixture
def logger(log_dir: Path) -> EffectLogger:
    return EffectLogger(str(log_dir))


@pytest.fixture(autouse=True)
def reset_effect_logger():
    """Ensure no logger leaks between tests."""
    original = ExecutionReport._effect_logger
    yield
    ExecutionReport._effect_logger = original


class TestAgentContext:
    def test_get_current_agent_default_none(self) -> None:
        assert get_current_agent() is None

    def test_agent_scope_sets_and_resets(self) -> None:
        assert get_current_agent() is None
        with agent_scope("analyst"):
            assert get_current_agent() == "analyst"
        assert get_current_agent() is None

    def test_agent_scope_nests(self) -> None:
        with agent_scope("analyst"):
            assert get_current_agent() == "analyst"
            with agent_scope("explorer"):
                assert get_current_agent() == "explorer"
            assert get_current_agent() == "analyst"


class TestEffectLogger:
    def test_writes_jsonl(self, logger: EffectLogger, log_dir: Path) -> None:
        effect = Effect(
            seq=0,
            effect_type="node_created",
            node=NodeRef(label="Statement", hash="abc1234"),
            patch={"text": "Hello"},
        )
        logger.log_effect("sid-123", "analyst", "SurfaceTheses", effect)

        log_file = log_dir / "sid-123" / "analyst.jsonl"
        assert log_file.exists()

        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 1

        record = json.loads(lines[0])
        assert record["type"] == "effect"
        assert record["tool"] == "SurfaceTheses"
        assert record["effect_type"] == "node_created"
        assert record["node"]["label"] == "Statement"
        assert record["node"]["hash"] == "abc1234"
        assert record["patch"]["text"] == "Hello"
        assert "ts" in record

    def test_creates_directories(self, logger: EffectLogger, log_dir: Path) -> None:
        effect = Effect(seq=0, effect_type="node_created", node=NodeRef(label="X", hash="h"))
        logger.log_effect("deep/nested/sid", "agent", "Tool", effect)

        assert (log_dir / "deep/nested/sid" / "agent.jsonl").exists()

    def test_tool_call_logging(self, logger: EffectLogger, log_dir: Path) -> None:
        logger.log_tool_call("sid-1", "analyst", "surface_theses", {"intent": "find"})

        log_file = log_dir / "sid-1" / "analyst.jsonl"
        record = json.loads(log_file.read_text().strip())
        assert record["type"] == "tool_call"
        assert record["tool"] == "surface_theses"
        assert record["args"] == {"intent": "find"}

    def test_tool_result_logging(self, logger: EffectLogger, log_dir: Path) -> None:
        logger.log_tool_result("sid-1", "analyst", "SurfaceTheses", True, "Done", 3)

        log_file = log_dir / "sid-1" / "analyst.jsonl"
        record = json.loads(log_file.read_text().strip())
        assert record["type"] == "tool_result"
        assert record["tool"] == "SurfaceTheses"
        assert record["ok"] is True
        assert record["summary"] == "Done"
        assert record["effect_count"] == 3

    def test_appends_multiple_entries(self, logger: EffectLogger, log_dir: Path) -> None:
        effect = Effect(seq=0, effect_type="node_created", node=NodeRef(label="A", hash="h1"))
        logger.log_effect("sid-1", "analyst", "T1", effect)
        logger.log_effect("sid-1", "analyst", "T2", effect)

        log_file = log_dir / "sid-1" / "analyst.jsonl"
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 2


class TestExecutionReportLogging:
    def test_logs_when_configured(self, logger: EffectLogger, log_dir: Path) -> None:
        ExecutionReport.set_effect_logger(logger)

        report = ExecutionReport(tool="TestTool")
        node = MagicMock()
        node.__class__.__name__ = "Statement"
        node.short_hash = "abc1234"
        node.text = "test text"

        with scope("test-sid"):
            with agent_scope("analyst"):
                report.node_created(node)

        log_file = log_dir / "test-sid" / "analyst.jsonl"
        assert log_file.exists()
        record = json.loads(log_file.read_text().strip())
        assert record["type"] == "effect"
        assert record["tool"] == "TestTool"

    def test_noop_when_no_logger(self, log_dir: Path) -> None:
        ExecutionReport.set_effect_logger(None)

        report = ExecutionReport(tool="TestTool")
        node = MagicMock()
        node.__class__.__name__ = "Statement"
        node.short_hash = "abc1234"
        node.text = "test text"

        with scope("test-sid"):
            with agent_scope("analyst"):
                report.node_created(node)

        assert not log_dir.exists()

    def test_falls_back_to_pipeline_when_no_agent_context(self, logger: EffectLogger, log_dir: Path) -> None:
        ExecutionReport.set_effect_logger(logger)

        report = ExecutionReport(tool="TestTool")
        node = MagicMock()
        node.__class__.__name__ = "Statement"
        node.short_hash = "abc1234"
        node.text = "test text"

        with scope("test-sid"):
            report.node_created(node)

        log_file = log_dir / "test-sid" / "pipeline.jsonl"
        assert log_file.exists()
        record = json.loads(log_file.read_text().strip())
        assert record["type"] == "effect"

    def test_noop_when_no_scope(self, logger: EffectLogger, log_dir: Path) -> None:
        ExecutionReport.set_effect_logger(logger)

        report = ExecutionReport(tool="TestTool")
        node = MagicMock()
        node.__class__.__name__ = "Statement"
        node.short_hash = "abc1234"
        node.text = "test text"

        with agent_scope("analyst"):
            report.node_created(node)

        assert not list(log_dir.glob("**/*.jsonl"))

    def test_finalize_logs_tool_result(self, logger: EffectLogger, log_dir: Path) -> None:
        ExecutionReport.set_effect_logger(logger)

        report = ExecutionReport(tool="TestTool", ok=True, summary="All good")
        node = MagicMock()
        node.__class__.__name__ = "Statement"
        node.short_hash = "abc1234"
        node.text = "test text"

        with scope("test-sid"):
            with agent_scope("analyst"):
                report.node_created(node)
                report.finalize()

        log_file = log_dir / "test-sid" / "analyst.jsonl"
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 2

        result_record = json.loads(lines[1])
        assert result_record["type"] == "tool_result"
        assert result_record["ok"] is True
        assert result_record["summary"] == "All good"
        assert result_record["effect_count"] == 1

    def test_finalize_idempotent(self, logger: EffectLogger, log_dir: Path) -> None:
        ExecutionReport.set_effect_logger(logger)

        report = ExecutionReport(tool="TestTool", ok=True, summary="Done")

        with scope("test-sid"):
            with agent_scope("analyst"):
                report.finalize()
                report.finalize()

        log_file = log_dir / "test-sid" / "analyst.jsonl"
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 1

    def test_str_triggers_finalize(self, logger: EffectLogger, log_dir: Path) -> None:
        ExecutionReport.set_effect_logger(logger)

        report = ExecutionReport(tool="TestTool", ok=True, summary="Via str")

        with scope("test-sid"):
            with agent_scope("analyst"):
                str(report)
                str(report)

        log_file = log_dir / "test-sid" / "analyst.jsonl"
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 1
