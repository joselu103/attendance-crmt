import asyncio

from attendance_crmt.server import create_server


def test_create_server_registers_catalog_tools(server_dependencies) -> None:
    server = create_server(server_dependencies)

    tools = asyncio.run(server.list_tools())

    assert server.name == "attendance-crmt"
    assert [tool.name for tool in tools] == ["list_employees"]
