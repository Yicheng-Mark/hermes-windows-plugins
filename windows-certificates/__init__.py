"""Hermes plugin entry point.

Install by cloning this directory into ``~/.hermes/plugins/hermes-windows-certificates``
(or ``hermes plugins install``), then enable it:

    hermes plugins enable hermes-windows-certificates

The plugin registers two read-only tools over the Windows certificate stores,
``win_cert_table`` and ``win_cert_detail``. See README.md for what they report
and what they cost.
"""


def register(ctx):
    from .hermes_windows_certificates import schemas, tools

    ctx.register_tool(
        name="win_cert_table",
        toolset="windows_certificates",
        schema=schemas.CERT_TABLE,
        handler=tools.win_cert_table,
    )
    ctx.register_tool(
        name="win_cert_detail",
        toolset="windows_certificates",
        schema=schemas.CERT_DETAIL,
        handler=tools.win_cert_detail,
    )
