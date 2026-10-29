"""Hermes plugin entry point.

Install by cloning this directory into ``~/.hermes/plugins/hermes-windows-services``
(or ``hermes plugins install``), then enable it:

    hermes plugins enable hermes-windows-services

The plugin registers two read-only tools over the Windows service manager,
``win_service_table`` and ``win_service_detail``. See README.md for what they report
and what they cost.
"""


def register(ctx):
    from .hermes_windows_services import schemas, tools

    ctx.register_tool(
        name="win_service_table",
        toolset="windows_services",
        schema=schemas.SERVICE_TABLE,
        handler=tools.win_service_table,
    )
    ctx.register_tool(
        name="win_service_detail",
        toolset="windows_services",
        schema=schemas.SERVICE_DETAIL,
        handler=tools.win_service_detail,
    )
