"""Client for remote MCP Streamable HTTP servers."""

from __future__ import annotations

import json
from typing import Any

import httpx


class MCPError(RuntimeError):
    pass


class MCPClient:
    """Small MCP client implementing initialize, tools/list and tools/call.

    ``server_url`` must be the actual Streamable HTTP endpoint (often ``/mcp``),
    not the root URL of a web site.
    """

    protocol_version = "2024-11-05"

    def __init__(self, server_url: str, timeout: float = 60.0, headers: dict[str, str] | None = None):
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout
        self.headers = headers or {}
        self._request_id = 0

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    @staticmethod
    def _decode_response(response: httpx.Response) -> dict[str, Any]:
        if "text/event-stream" in response.headers.get("content-type", ""):
            for line in response.text.splitlines():
                if line.startswith("data:"):
                    data = json.loads(line[5:].strip())
                    if isinstance(data, dict) and ("result" in data or "error" in data):
                        return data
            raise MCPError("MCP server returned no JSON-RPC result in SSE response")
        try:
            data = response.json()
        except ValueError as exc:
            raise MCPError("MCP server returned a non-JSON response") from exc
        if not isinstance(data, dict):
            raise MCPError("MCP server returned an invalid JSON-RPC response")
        return data

    async def _rpc(
        self,
        client: httpx.AsyncClient,
        method: str,
        params: dict[str, Any] | None = None,
        session_id: str | None = None,
        notification: bool = False,
    ) -> tuple[dict[str, Any], str | None]:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if not notification:
            payload["id"] = self._next_id()
        if params is not None:
            payload["params"] = params
        headers = {**self.headers, "Accept": "application/json, text/event-stream"}
        if session_id:
            headers["Mcp-Session-Id"] = session_id
        response = await client.post(self.server_url, json=payload, headers=headers)
        response.raise_for_status()
        new_session_id = response.headers.get("Mcp-Session-Id") or session_id
        if notification or response.status_code == 202 or not response.content:
            return {}, new_session_id
        data = self._decode_response(response)
        if "error" in data:
            error = data["error"]
            raise MCPError(error.get("message", str(error)) if isinstance(error, dict) else str(error))
        return data.get("result", {}), new_session_id

    async def _initialize(self, client: httpx.AsyncClient) -> str | None:
        _, session_id = await self._rpc(client, "initialize", {
            "protocolVersion": self.protocol_version,
            "capabilities": {},
            "clientInfo": {"name": "smartcare", "version": "1.0.0"},
        })
        # Do not block registration on the optional initialized notification.
        # Some stateless public servers accept tools/list immediately but never
        # finish the notification HTTP response (mcpub.dev is one example).
        return session_id

    async def list_tools(self) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            session_id = await self._initialize(client)
            result, _ = await self._rpc(client, "tools/list", {}, session_id)
        tools = result.get("tools", [])
        if not isinstance(tools, list):
            raise MCPError("MCP tools/list returned an invalid tools value")
        return [
            {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("inputSchema", {"type": "object", "properties": {}}),
                "annotations": tool.get("annotations", {}),
            }
            for tool in tools
            if isinstance(tool, dict) and tool.get("name")
        ]

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            session_id = await self._initialize(client)
            result, _ = await self._rpc(client, "tools/call", {
                "name": tool_name,
                "arguments": arguments,
            }, session_id)
        return {"status": "failed" if result.get("isError") else "success", "result": result}

    async def health_check(self) -> dict[str, Any]:
        try:
            tools = await self.list_tools()
            return {"status": "healthy", "tools_count": len(tools)}
        except Exception as exc:
            return {"status": "unreachable", "error": str(exc)}
