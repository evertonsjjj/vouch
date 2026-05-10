"""MCP server — exposes ``search_curated_sources`` over stdio.

Usage::

    curio mcp serve --catalog sites.yaml

Then point Claude Desktop / Cursor / Cline at the binary in their MCP config.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from ..engine import SearchEngine

log = logging.getLogger("curio.mcp")


def run_stdio_server(*, catalog_path: Path, llm: str = "ollama/qwen2.5:14b") -> None:
    try:
        from mcp.server import Server  # type: ignore
        from mcp.server.stdio import stdio_server  # type: ignore
        from mcp.types import TextContent, Tool  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "MCP integration requires the mcp package. pip install 'curio[mcp]'"
        ) from e

    engine = SearchEngine.from_yaml(catalog_path, llm=llm)
    server = Server("curio")

    @server.list_tools()
    async def _list() -> list[Tool]:
        return [
            Tool(
                name="search_curated_sources",
                description=(
                    "Search the user's curated list of trusted sources. "
                    "Returns titles, URLs, and snippets ranked by relevance."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "depth": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 3,
                            "default": 1,
                            "description": "0=homepage, 1=results, 2=full content, 3=deep crawl",
                        },
                        "max_results": {"type": "integer", "default": 10},
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="list_sources",
                description="List all sites currently in the user's catalog.",
                inputSchema={"type": "object", "properties": {}},
            ),
        ]

    @server.call_tool()
    async def _call(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        if name == "list_sources":
            payload = engine.catalog.to_dicts()
            return [TextContent(type="text", text=json.dumps(payload, indent=2))]
        if name == "search_curated_sources":
            query = arguments["query"]
            depth = int(arguments.get("depth", 1))
            max_results = int(arguments.get("max_results", 10))
            result = await asyncio.to_thread(
                engine.search, query, depth=depth, max_results=max_results
            )
            return [TextContent(type="text", text=result.to_text())]
        return [TextContent(type="text", text=f"unknown tool: {name}")]

    async def _main():
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    asyncio.run(_main())


__all__ = ["run_stdio_server"]
