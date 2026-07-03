"""Check configured MCP endpoints from the API runtime network."""

import asyncio

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.mcp.client import MCPClient
from app.models.models import MCPServerConfig


async def main() -> None:
    async with AsyncSessionLocal() as db:
        servers = (await db.execute(select(MCPServerConfig))).scalars().all()
    for server in servers:
        try:
            tools = await MCPClient(
                server.url,
                headers=__import__("json").loads(server.headers_json or "{}"),
            ).list_tools()
            print(f"{server.server_key}: OK ({len(tools)} tools)")
        except Exception as exc:
            print(f"{server.server_key}: FAIL ({exc})")


if __name__ == "__main__":
    asyncio.run(main())
