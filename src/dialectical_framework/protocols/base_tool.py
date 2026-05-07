from __future__ import annotations

from abc import abstractmethod
from typing import Any

from pydantic import BaseModel


class BaseTool(BaseModel):
    """Base class for tool definitions.

    Pydantic fields define the LLM-visible parameters (tool schema).
    The call() method contains execution logic with DI injection.
    """

    def model_post_init(self, __context: Any) -> None:
        from dialectical_framework.agents.execution_report import ExecutionReport
        object.__setattr__(self, "_report", ExecutionReport(tool=self.__class__.__name__))

    @abstractmethod
    async def call(self) -> str: ...
