"""A thin, real MCP client over stdio, independent of the ADK McpToolset
used in src/adk_app/agents.py. The benchmark orchestrators in this package
talk to the two real MCP servers through this client directly, not through
ADK, because no model credentials exist in this session to drive ADK's own
LlmAgent event loop (see src/adk_app/agents.py's module docstring). The MCP
protocol handshake, tool listing and tool calls below are genuine; nothing
here is mocked.
"""

from __future__ import annotations

import json
import sys
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class McpServerClient:
    def __init__(self, server_module: str):
        self._server_module = server_module
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> "McpServerClient":
        self._stack = AsyncExitStack()
        params = StdioServerParameters(command=sys.executable, args=["-m", self._server_module])
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self._session = await self._stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self._stack.aclose()

    async def list_tool_names(self) -> list[str]:
        result = await self._session.list_tools()
        return [t.name for t in result.tools]

    async def call(self, tool_name: str, **kwargs) -> dict:
        result = await self._session.call_tool(tool_name, kwargs)
        if not result.content:
            return {}
        text = result.content[0].text
        if result.is_error:
            raise RuntimeError(f"MCP protocol-level error calling {tool_name}({kwargs}): {text}")
        return json.loads(text)
