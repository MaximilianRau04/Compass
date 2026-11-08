"""The MCP interface as an assistant sees it: tool names, parameters, output schemas, annotations
and prompts. Connected assistants rely on it, so a change must be deliberate.

After an intended change, update the fixture:

    UPDATE_MCP_CONTRACT=1 uv run pytest tests/test_mcp_contract.py
"""

import json
import os
from pathlib import Path

import pytest
from mcp import Client

from app.mcp.server import mcp

FIXTURE = Path(__file__).parent / "fixtures" / "mcp_contract.json"


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def contract() -> dict:
    async with Client(mcp, raise_exceptions=True) as c:
        tools = (await c.list_tools()).tools
        prompts = (await c.list_prompts()).prompts

    def dump(item) -> dict:
        return item.model_dump(mode="json", by_alias=True, exclude_none=True)

    return {
        "tools": {t.name: dump(t) for t in tools},
        "prompts": {p.name: dump(p) for p in prompts},
    }


@pytest.mark.anyio
async def test_mcp_contract_unchanged():
    current = await contract()
    if os.environ.get("UPDATE_MCP_CONTRACT"):
        FIXTURE.write_text(json.dumps(current, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    expected = json.loads(FIXTURE.read_text())
    assert sorted(current["tools"]) == sorted(expected["tools"])
    assert sorted(current["prompts"]) == sorted(expected["prompts"])
    for name, tool in expected["tools"].items():
        assert current["tools"][name] == tool, f"tool {name} changed"
    for name, prompt in expected["prompts"].items():
        assert current["prompts"][name] == prompt, f"prompt {name} changed"
