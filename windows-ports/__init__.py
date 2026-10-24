"""Hermes plugin entry point.

Install by cloning this repository into ``~/.hermes/plugins/hermes-windows-ports``
(or ``hermes plugins install``), then enable it:

    hermes plugins enable hermes-windows-ports

The plugin registers one read-only tool, ``win_port_owners``, over the Windows TCP/UDP
owner tables. See README.md for the filters and the output shape.
"""


def register(ctx):
    from .hermes_windows_ports import schemas, tools

    ctx.register_tool(
        name="win_port_owners",
        toolset="windows_ports",
        schema=schemas.PORT_OWNERS,
        handler=tools.win_port_owners,
    )
