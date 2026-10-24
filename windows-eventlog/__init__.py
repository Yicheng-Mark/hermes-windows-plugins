"""Hermes plugin entry point.

Install by cloning this repository into ``~/.hermes/plugins/hermes-windows-eventlog``
(or ``hermes plugins install``), then enable it:

    hermes plugins enable hermes-windows-eventlog

The plugin registers three read-only tools over the Windows Event Log:
``win_crash_events``, ``win_shutdown_events`` and ``win_eventlog_query``.
See README.md for what each one answers.
"""


def register(ctx):
    from .hermes_windows_eventlog import schemas, tools

    for name, schema, handler in (
        ("win_crash_events", schemas.CRASH_EVENTS, tools.win_crash_events),
        ("win_shutdown_events", schemas.SHUTDOWN_EVENTS, tools.win_shutdown_events),
        ("win_eventlog_query", schemas.EVENTLOG_QUERY, tools.win_eventlog_query),
    ):
        ctx.register_tool(
            name=name,
            toolset="windows_eventlog",
            schema=schema,
            handler=handler,
        )
