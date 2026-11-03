"""Hermes plugin entry point.

Install by cloning this directory into ``~/.hermes/plugins/hermes-windows-startup``
(or ``hermes plugins install``), then enable it:

    hermes plugins enable hermes-windows-startup

The plugin registers two read-only tools over Windows autostart,
``win_startup_table`` and ``win_startup_detail``. See README.md for what they
report and what they cost.
"""


def register(ctx):
    from .hermes_windows_startup import schemas, tools

    ctx.register_tool(
        name="win_startup_table",
        toolset="windows_startup",
        schema=schemas.STARTUP_TABLE,
        handler=tools.win_startup_table,
    )
    ctx.register_tool(
        name="win_startup_detail",
        toolset="windows_startup",
        schema=schemas.STARTUP_DETAIL,
        handler=tools.win_startup_detail,
    )
