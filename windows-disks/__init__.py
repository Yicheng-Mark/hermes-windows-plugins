"""Hermes plugin entry point.

Install by cloning this directory into ``~/.hermes/plugins/hermes-windows-disks``
(or ``hermes plugins install``), then enable it:

    hermes plugins enable hermes-windows-disks

The plugin registers two read-only tools over the Windows storage stack's own
view of the machine, ``win_disk_table`` and ``win_disk_detail``. See README.md
for what they report and what they cost.
"""


def register(ctx):
    from .hermes_windows_disks import schemas, tools

    ctx.register_tool(
        name="win_disk_table",
        toolset="windows_disks",
        schema=schemas.DISK_TABLE,
        handler=tools.win_disk_table,
    )
    ctx.register_tool(
        name="win_disk_detail",
        toolset="windows_disks",
        schema=schemas.DISK_DETAIL,
        handler=tools.win_disk_detail,
    )
