"""
EffectLogger: File-based JSONL logger for graph mutation effects.

Writes one JSON object per line to: <log_dir>/<sid>/<agent_name>.jsonl

Lifecycle:
    logger = EffectLogger(log_dir="/tmp/effects")
    ExecutionReport.set_effect_logger(logger)
    # ... effects are logged automatically ...
    ExecutionReport.set_effect_logger(None)  # teardown
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dialectical_framework.agents.execution_report import Effect


class EffectLogger:
    """
    Synchronous file-based effect logger.

    Thread-safe via a per-file lock dict. Creates directories lazily.
    """

    def __init__(self, log_dir: str) -> None:
        self._log_dir = Path(log_dir).resolve()
        self._locks: dict[Path, threading.Lock] = {}
        self._global_lock = threading.Lock()

    def _get_lock(self, path: Path) -> threading.Lock:
        with self._global_lock:
            if path not in self._locks:
                self._locks[path] = threading.Lock()
            return self._locks[path]

    def _resolve_path(self, sid: str, agent: str) -> Path:
        return self._log_dir / sid / f"{agent}.jsonl"

    def _write_line(self, path: Path, record: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, default=str) + "\n"
        lock = self._get_lock(path)
        with lock:
            with open(path, "a") as f:
                f.write(line)

    def log_effect(
        self,
        sid: str,
        agent: str,
        tool: str,
        effect: Effect,
    ) -> None:
        """Append a single effect as a JSONL line."""
        path = self._resolve_path(sid, agent)
        record = {
            "ts": time.time(),
            "type": "effect",
            "tool": tool,
            **effect.model_dump(exclude_none=True),
        }
        self._write_line(path, record)

    def log_tool_call(
        self,
        sid: str,
        agent: str,
        tool_name: str,
        tool_args: dict[str, Any],
    ) -> None:
        """Append a tool invocation entry."""
        path = self._resolve_path(sid, agent)
        record = {
            "ts": time.time(),
            "type": "tool_call",
            "tool": tool_name,
            "args": tool_args,
        }
        self._write_line(path, record)

    def log_tool_result(
        self,
        sid: str,
        agent: str,
        tool: str,
        ok: bool,
        summary: str,
        effect_count: int,
    ) -> None:
        """Append a report-complete marker."""
        path = self._resolve_path(sid, agent)
        record = {
            "ts": time.time(),
            "type": "tool_result",
            "tool": tool,
            "ok": ok,
            "summary": summary,
            "effect_count": effect_count,
        }
        self._write_line(path, record)
