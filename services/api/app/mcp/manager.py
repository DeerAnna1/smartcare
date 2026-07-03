from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import socket
import time
from dataclasses import dataclass
from urllib.parse import urlparse

from app.core.config import get_settings
from app.mcp.client import MCPClient


class MCPConfigurationError(ValueError):
    pass


@dataclass
class CachedTools:
    fingerprint: str
    expires_at: float
    tools: list[dict]


class MCPManager:
    """Multi-server MCP discovery/invocation with cache and SSRF controls."""

    def __init__(self, cache_ttl: int = 300):
        self.cache_ttl = cache_ttl
        self._cache: dict[str, CachedTools] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def validate_http_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise MCPConfigurationError("MCP URL 必须是有效的 http/https 地址")
        if parsed.username or parsed.password:
            raise MCPConfigurationError("MCP URL 不允许内嵌用户名或密码")
        if get_settings().ENV == "development" and parsed.hostname in ("localhost", "127.0.0.1", "host.docker.internal"):
            return
        if parsed.scheme != "https":
            raise MCPConfigurationError("非开发环境 MCP 必须使用 HTTPS")
        try:
            addresses = await asyncio.to_thread(socket.getaddrinfo, parsed.hostname, parsed.port or 443)
        except socket.gaierror as exc:
            raise MCPConfigurationError(f"MCP 域名无法解析: {parsed.hostname}") from exc
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            # Docker Desktop's DNS/proxy layer maps public destinations to the
            # RFC 2544 benchmarking range. It is safe to allow only in local
            # development; production keeps the full SSRF restriction.
            if (
                get_settings().ENV == "development"
                and ip in ipaddress.ip_network("198.18.0.0/15")
            ):
                continue
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
                raise MCPConfigurationError("MCP 地址解析到受限网络，已阻止 SSRF 请求")

    @staticmethod
    def _fingerprint(config: dict) -> str:
        safe = {k: config.get(k) for k in ("transport", "url", "command", "args", "headers", "enabled")}
        return hashlib.sha256(json.dumps(safe, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    async def discover(self, server_key: str, config: dict, force: bool = False) -> list[dict]:
        if not config.get("enabled", True):
            return []
        transport = config.get("transport", "http")
        if transport != "http":
            raise MCPConfigurationError("当前运行时只实现了 Streamable HTTP MCP；SSE/stdio 尚未启用")
        url = config.get("url", "")
        await self.validate_http_url(url)
        fingerprint = self._fingerprint(config)
        cached = self._cache.get(server_key)
        if not force and cached and cached.fingerprint == fingerprint and cached.expires_at > time.time():
            return cached.tools
        lock = self._locks.setdefault(server_key, asyncio.Lock())
        async with lock:
            cached = self._cache.get(server_key)
            if not force and cached and cached.fingerprint == fingerprint and cached.expires_at > time.time():
                return cached.tools
            tools = await MCPClient(url, headers=config.get("headers") or {}).list_tools()
            normalized = [{
                **tool,
                "original_name": tool["name"],
                "name": f"{server_key}__{tool['name']}",
                "namespace": server_key,
            } for tool in tools]
            self._cache[server_key] = CachedTools(fingerprint, time.time() + self.cache_ttl, normalized)
            return normalized

    async def invoke(self, config: dict, exposed_tool_name: str, arguments: dict) -> dict:
        server_key = config["server_key"]
        prefix = f"{server_key}__"
        original_name = exposed_tool_name[len(prefix):] if exposed_tool_name.startswith(prefix) else exposed_tool_name
        await self.validate_http_url(config["url"])
        return await MCPClient(config["url"], headers=config.get("headers") or {}).call_tool(original_name, arguments)

    def invalidate(self, server_key: str | None = None) -> None:
        if server_key is None:
            self._cache.clear()
        else:
            self._cache.pop(server_key, None)


mcp_manager = MCPManager()
