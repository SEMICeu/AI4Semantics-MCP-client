from asyncio import (
    run,
)
from clients import (
    MCPClient,
)


async def main() -> None:
    state = {
        "user": "Gabriel",
        "name": "test_add_class",
        "package": "madeup",
        "ID": "id",
    }
    url = "http://localhost:8001/mcp/"
    async with MCPClient(state, url) as mcp_client:
        server_tools = (await mcp_client.session.list_tools()).tools
        print(
            {
                tool.name: tool.description
                for tool
                in server_tools
            },
            sep="\n\n",
        )


if __name__ == "__main__":
    run(main())
