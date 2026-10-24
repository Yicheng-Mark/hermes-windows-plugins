"""Hermes plugin entry point.

Install by cloning this repository into ``~/.hermes/plugins/hermes-wincred`` (or with
``hermes plugins install``), then enable the source and map the variables you want:

    hermes plugins enable hermes-wincred
    hermes config set secrets.wincred.enabled true

Credentials themselves are read from the current user's Windows Credential Manager at
startup. See README.md for how to store them.
"""


def register(ctx):
    from .hermes_wincred.source import WinCredSource

    ctx.register_secret_source(WinCredSource())
