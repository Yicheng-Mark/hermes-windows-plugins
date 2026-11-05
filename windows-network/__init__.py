"""Hermes plugin entry point.

Install by cloning this directory into ``~/.hermes/plugins/hermes-windows-network``
(or ``hermes plugins install``), then enable it:

    hermes plugins enable hermes-windows-network

The plugin registers two read-only tools over the machine's network adapters,
``win_adapter_table`` and ``win_adapter_detail``. See README.md for what they
report and what they cost.
"""


def register(ctx):
    from .hermes_windows_network import schemas, tools

    ctx.register_tool(
        name="win_adapter_table",
        toolset="windows_network",
        schema=schemas.ADAPTER_TABLE,
        handler=tools.win_adapter_table,
    )
    ctx.register_tool(
        name="win_adapter_detail",
        toolset="windows_network",
        schema=schemas.ADAPTER_DETAIL,
        handler=tools.win_adapter_detail,
    )
