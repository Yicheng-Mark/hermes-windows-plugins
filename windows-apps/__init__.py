"""Hermes plugin entry point.

Install by cloning this directory into ``~/.hermes/plugins/hermes-windows-apps``
(or ``hermes plugins install``), then enable it:

    hermes plugins enable hermes-windows-apps

The plugin registers two read-only tools over installed software,
``win_app_table`` and ``win_app_detail``. See README.md for what they
report and what they cost.
"""


def register(ctx):
    from .hermes_windows_apps import schemas, tools

    ctx.register_tool(
        name="win_app_table",
        toolset="windows_apps",
        schema=schemas.APP_TABLE,
        handler=tools.win_app_table,
    )
    ctx.register_tool(
        name="win_app_detail",
        toolset="windows_apps",
        schema=schemas.APP_DETAIL,
        handler=tools.win_app_detail,
    )
