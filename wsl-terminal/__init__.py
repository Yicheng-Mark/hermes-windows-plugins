"""Hermes plugin entry point.

Install by cloning this repository into ``~/.hermes/plugins/hermes-wsl-terminal`` (or with
``hermes plugins install``), then select the backend:

    hermes plugins enable hermes-wsl-terminal
    hermes config set terminal.backend wsl
"""


def register(ctx):
    from .hermes_wsl_terminal.provider import WslProvider

    ctx.register_terminal_environment_provider(WslProvider())
