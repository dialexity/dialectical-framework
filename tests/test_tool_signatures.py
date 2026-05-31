"""
Tests for @llm.tool function signatures.

Verifies that tool functions can be called with only required args (simulating
what happens when an LLM omits optional parameters from its JSON response).
Mirascope's execute() deserializes JSON kwargs and calls the function — omitted
optional params must fall back to proper Python defaults, not FieldInfo objects.
"""

from __future__ import annotations

import inspect
import json

import pytest
from mirascope.llm.content import ToolCall
from mirascope.llm.tools.tool_schema import ToolSchema
from pydantic.fields import FieldInfo

from dialectical_framework.agents.analyst.analyst import analyze
from dialectical_framework.agents.analyst.skills.edit_perspective import (
    edit_perspective,
)
from dialectical_framework.agents.analyst.skills.expand_polarities import (
    expand_polarities,
)
from dialectical_framework.agents.analyst.skills.find_polarities import (
    find_polarities,
)
from dialectical_framework.agents.analyst.skills.introduce_polarity import (
    introduce_polarity,
)
from dialectical_framework.agents.analyst.skills.anchor_theses import anchor_theses
from dialectical_framework.agents.analyst.skills.surface_theses import surface_theses
from dialectical_framework.agents.analyst.tools.create_dx_input import create_dx_input
from dialectical_framework.agents.analyst.tools.place_statement import place_statement
from dialectical_framework.agents.explorer.explorer import explore
from dialectical_framework.agents.explorer.skills.build_wheels import build_wheels
from dialectical_framework.agents.explorer.skills.explore_transformations import (
    explore_transformations,
)
from dialectical_framework.agents.explorer.tools.create_nexus import create_nexus
from dialectical_framework.agents.explorer.tools.present_exploration import (
    present_exploration,
)
from dialectical_framework.agents.orchestrator.tools.add_input import add_input
from dialectical_framework.agents.orchestrator.tools.inspect_node import inspect_node
from dialectical_framework.agents.orchestrator.tools.query_graph import query_graph
from dialectical_framework.agents.orchestrator.tools.reject import reject

ALL_TOOLS = [
    analyze,
    anchor_theses,
    surface_theses,
    find_polarities,
    expand_polarities,
    edit_perspective,
    introduce_polarity,
    place_statement,
    create_dx_input,
    explore,
    build_wheels,
    explore_transformations,
    create_nexus,
    present_exploration,
    add_input,
    inspect_node,
    query_graph,
    reject,
]


class TestToolDefaultsAreNotFieldInfo:
    """No @llm.tool parameter should have FieldInfo as its Python default."""

    @pytest.mark.parametrize("tool_fn", ALL_TOOLS, ids=lambda f: f.__name__)
    def test_no_fieldinfo_defaults(self, tool_fn):
        sig = inspect.signature(tool_fn)
        for name, param in sig.parameters.items():
            assert not isinstance(param.default, FieldInfo), (
                f"{tool_fn.__name__}({name}) has FieldInfo as default — "
                f"use Annotated[type, Field(...)] = actual_default instead"
            )


class TestToolSchemaGeneration:
    """Mirascope generates valid schemas with descriptions from Annotated."""

    @pytest.mark.parametrize("tool_fn", ALL_TOOLS, ids=lambda f: f.__name__)
    def test_schema_has_descriptions(self, tool_fn):
        schema = ToolSchema.from_function(tool_fn)
        for prop_name, prop_schema in schema.parameters.properties.items():
            assert "description" in prop_schema, (
                f"{tool_fn.__name__}.{prop_name} missing description in schema"
            )


class TestToolExecuteWithRequiredOnly:
    """Simulate Mirascope execute(): call tool with only required JSON args."""

    @pytest.mark.parametrize("tool_fn", ALL_TOOLS, ids=lambda f: f.__name__)
    def test_required_only_kwargs_dont_crash_on_defaults(self, tool_fn):
        schema = ToolSchema.from_function(tool_fn)
        required = set(schema.parameters.required)
        props = schema.parameters.properties

        required_kwargs = {}
        for name in required:
            prop = props[name]
            prop_type = prop.get("type", "")
            if prop_type == "string":
                required_kwargs[name] = "test-value"
            elif prop_type == "integer":
                required_kwargs[name] = 1
            elif prop_type == "array":
                required_kwargs[name] = ["test-hash"]
            elif prop_type == "object":
                required_kwargs[name] = {"T": "test"}
            else:
                required_kwargs[name] = "test-value"

        tool_call = ToolCall(
            id="test-call-id",
            name=tool_fn.__name__,
            args=json.dumps(required_kwargs),
        )

        sig = inspect.signature(tool_fn)
        kwargs_from_json = json.loads(tool_call.args)
        for name, param in sig.parameters.items():
            if name not in kwargs_from_json:
                assert param.default is not inspect.Parameter.empty, (
                    f"{tool_fn.__name__}({name}) is not in JSON and has no default"
                )
                assert not isinstance(param.default, FieldInfo), (
                    f"{tool_fn.__name__}({name}) would receive FieldInfo at runtime"
                )
