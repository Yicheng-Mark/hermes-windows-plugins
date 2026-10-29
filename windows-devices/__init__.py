"""Hermes plugin entry point.

Install by cloning this directory into ``~/.hermes/plugins/hermes-windows-devices``
(or ``hermes plugins install``), then enable it:

    hermes plugins enable hermes-windows-devices

The plugin registers two read-only tools over the Plug-and-Play device tree,
``win_device_table`` and ``win_device_detail``. See README.md for what they report
and what they cost.
"""


def register(ctx):
    from .hermes_windows_devices import schemas, tools

    ctx.register_tool(
        name="win_device_table",
        toolset="windows_devices",
        schema=schemas.DEVICE_TABLE,
        handler=tools.win_device_table,
    )
    ctx.register_tool(
        name="win_device_detail",
        toolset="windows_devices",
        schema=schemas.DEVICE_DETAIL,
        handler=tools.win_device_detail,
    )
