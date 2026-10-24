"""Hermes plugin entry point.

Install by cloning this repository into ``~/.hermes/plugins/hermes-dpapi-secrets`` (or
with ``hermes plugins install``), create the store, then enable the source and map the
variables you want:

    python -m hermes_dpapi_secrets set OPENAI_API_KEY
    hermes plugins enable hermes-dpapi-secrets
    hermes config set secrets.dpapi.enabled true

The store is one DPAPI-encrypted blob readable only by the Windows user that wrote it.
See README.md for the config layout.
"""


def register(ctx):
    from .hermes_dpapi_secrets.source import DpapiSecretsSource

    ctx.register_secret_source(DpapiSecretsSource())
