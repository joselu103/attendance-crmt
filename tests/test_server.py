import asyncio

from attendance_crmt.server import create_server


def test_create_server_registers_echo_tool() -> None:
    server = create_server()

    tools = asyncio.run(server.list_tools())

    assert server.name == "attendance-crmt"
    assert [tool.name for tool in tools] == ["echo", "list_employees"]


def test_echo_tool_returns_the_supplied_message() -> None:
    server = create_server()

    result = asyncio.run(server.call_tool("echo", {"message": "Hello, MCP!"}))

    assert result.is_error is False
    assert result.content[0].text == "Hello, MCP!"
