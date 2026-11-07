"""Hermes plugin entry point.

Install by cloning this directory into ``~/.hermes/plugins/hermes-windows-firewall``
(or ``hermes plugins install``), then enable it:

    hermes plugins enable hermes-windows-firewall

The plugin registers two read-only tools over the Windows firewall's own
registry store, ``win_firewall_table`` and ``win_firewall_detail``. See
README.md for what they report and what they cost.
"""


def register(ctx):
    from .hermes_windows_firewall import schemas, tools

    ctx.register_tool(
        name="win_firewall_table",
        toolset="windows_firewall",
        schema=schemas.FIREWALL_TABLE,
        handler=tools.win_firewall_table,
    )
    ctx.register_tool(
        name="win_firewall_detail",
        toolset="windows_firewall",
        schema=schemas.FIREWALL_DETAIL,
        handler=tools.win_firewall_detail,
    )
