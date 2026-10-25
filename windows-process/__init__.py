"""Hermes plugin entry point.

Install by cloning this directory into ``~/.hermes/plugins/hermes-windows-process``
(or ``hermes plugins install``), then enable it:

    hermes plugins enable hermes-windows-process

The plugin registers one read-only tool, ``win_process_table``, over the Windows process
table. See README.md for the filters and the output shape.
"""


def register(ctx):
    from .hermes_windows_process import schemas, tools

    ctx.register_tool(
        name="win_process_table",
        toolset="windows_process",
        schema=schemas.PROCESS_TABLE,
        handler=tools.win_process_table,
    )
