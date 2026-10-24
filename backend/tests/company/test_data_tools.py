from company import data_tools


def test_overview_numbers():
    overview = data_tools.company_overview()
    assert overview["monthly_sales"] == 700000
    assert overview["gross_margin"] == 0.22
    assert "Stamford" in overview["q4_goal"]


def test_lackawanna_blocked_by_infinity():
    deal = data_tools.get_deal("lackawanna")
    assert "bulk discount" in deal["blocker"].lower()
    assert deal["value_per_year"] == 120000


def test_get_deal_unknown_returns_none():
    assert data_tools.get_deal("Initech") is None


def test_pipeline_has_about_fifteen_deals():
    deals = data_tools.get_pipeline()
    assert 12 <= len(deals) <= 18
    assert {"account", "value_per_year", "stage", "owner", "blocker"} <= set(deals[0])


def test_financials_match_overview():
    fin = data_tools.get_financials()
    assert len(fin["months"]) == 12
    assert fin["monthly_sales"] == fin["months"][-1]["sales"] == 700000
    assert fin["gross_margin"] == 0.22


def test_inbox_has_wallace():
    inbox = data_tools.read_inbox()
    assert any("David Wallace" in e["from"] for e in inbox)
    assert all("body" not in e for e in inbox)


def test_read_email_returns_body():
    first = data_tools.read_inbox()[0]
    email = data_tools.read_email(first["id"])
    assert email["subject"] == first["subject"]
    assert email["body"]


def test_read_email_unknown_returns_none():
    assert data_tools.read_email("nope") is None


def test_lookup_bulk_discount():
    text = data_tools.lookup_company("bulk discount")["matches"][0]["text"]
    assert "10%" in text and "50" in text


def test_lookup_limits_matches_and_length():
    matches = data_tools.lookup_company("the branch")["matches"]
    assert len(matches) <= 3
    assert all(len(m["text"]) <= 600 for m in matches)


def test_lookup_short_terms_like_q4():
    assert data_tools.lookup_company("Q4")["matches"][0]["section"] == "Q4 goals"


def test_lookup_team_finds_org_chart():
    sections = [m["section"] for m in data_tools.lookup_company("who is on the team")["matches"]]
    assert sections[0] == "Org chart and team"


def test_lookup_no_match():
    assert data_tools.lookup_company("zebra")["matches"] == []
