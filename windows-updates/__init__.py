"""Hermes plugin entry point.

Install by cloning this directory into ``~/.hermes/plugins/hermes-windows-updates``
(or ``hermes plugins install``), then enable it:

    hermes plugins enable hermes-windows-updates

The plugin registers two read-only tools over the Windows Update Agent's history,
``win_update_history`` and ``win_hotfix_table``. See README.md for what they report
and what they cost.
"""


def register(ctx):
    from .hermes_windows_updates import schemas, tools

    ctx.register_tool(
        name="win_update_history",
        toolset="windows_updates",
        schema=schemas.UPDATE_HISTORY,
        handler=tools.win_update_history,
    )
    ctx.register_tool(
        name="win_hotfix_table",
        toolset="windows_updates",
        schema=schemas.HOTFIX_TABLE,
        handler=tools.win_hotfix_table,
    )
