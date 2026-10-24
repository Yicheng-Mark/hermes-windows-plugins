"""Run the repository's own contract suite against this backend.

Requires the Hermes source tree on ``PYTHONPATH``::

    PYTHONPATH=/path/to/hermes-agent python -m pytest tests/test_conformance.py
"""

import pytest

pytest.importorskip(
    "agent.secret_sources.registry",
    reason="Hermes core is not installed; the catalog validator checks the real contract",
)

from tests.secret_sources.conformance import SecretSourceConformance  # noqa: E402

from hermes_dpapi_secrets.source import DpapiSecretsSource  # noqa: E402


class TestDpapiSecretsConformance(SecretSourceConformance):
    @pytest.fixture
    def source(self):
        return DpapiSecretsSource()
