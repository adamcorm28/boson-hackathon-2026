from types import SimpleNamespace

import pytest

from company.mock import MockCompany
from gateway import company_compat
from gateway.roles import FIXTURE_ROLES_DIR, load_roles


@pytest.fixture
def roles():
    return load_roles(FIXTURE_ROLES_DIR)


@pytest.fixture
def company():
    return MockCompany()


@pytest.fixture
def fake_data_tools(monkeypatch):
    """Pin data_tools so tests pass whether or not B2's module has landed."""
    fake = SimpleNamespace(
        company_overview=lambda: {"branch": "Scranton", "monthly_sales": 700000, "gross_margin": 0.22},
        get_pipeline=lambda: [{"account": "Lackawanna County Schools", "value_per_year": 120000}],
        get_deal=lambda name: {"account": "Lackawanna County Schools"} if "lacka" in name.lower() else None,
        get_financials=lambda: {"monthly_sales": 700000},
        read_inbox=lambda: [{"id": "e1", "from": "David Wallace"}],
        read_email=lambda email_id: {"id": "e1", "body": "Q4 please"} if email_id == "e1" else None,
        lookup_company=lambda topic: {"topic": topic, "matches": []},
    )
    monkeypatch.setattr(company_compat, "data_tools", lambda: fake)
    return fake
