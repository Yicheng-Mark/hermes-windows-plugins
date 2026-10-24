"""WSL distro (``wsl``) terminal backend for Hermes Agent.

Deliberately import-free: :mod:`hermes_wsl_terminal.config` and :mod:`hermes_wsl_terminal.wsl`
are pure stdlib and are unit-tested without a Hermes checkout, while
:mod:`hermes_wsl_terminal.provider` and :mod:`hermes_wsl_terminal.environment` import Hermes
and are only loadable inside a running Hermes. Importing them here would make the stdlib
layer untestable on its own.
"""
