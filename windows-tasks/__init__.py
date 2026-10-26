"""Hermes plugin entry point.

Install by cloning this directory into ``~/.hermes/plugins/hermes-windows-tasks``
(or ``hermes plugins install``), then enable it:

    hermes plugins enable hermes-windows-tasks

The plugin registers two read-only tools over Task Scheduler, ``win_scheduled_tasks`` and
``win_scheduled_task_detail``. See README.md for what they report and what they cost.
"""


def register(ctx):
    from .hermes_windows_tasks import schemas, tools

    ctx.register_tool(
        name="win_scheduled_tasks",
        toolset="windows_tasks",
        schema=schemas.SCHEDULED_TASKS,
        handler=tools.win_scheduled_tasks,
    )
    ctx.register_tool(
        name="win_scheduled_task_detail",
        toolset="windows_tasks",
        schema=schemas.SCHEDULED_TASK_DETAIL,
        handler=tools.win_scheduled_task_detail,
    )
