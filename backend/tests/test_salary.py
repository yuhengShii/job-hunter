from backend.app.services.salary import parse_salary


def test_prd_rules():
    assert parse_salary("8千-1.2万") == (8000, 12000)
    assert parse_salary("1.5-2万/月") == (15000, 20000)
    assert parse_salary("15-20K") == (15000, 20000)
    assert parse_salary("15-20k") == (15000, 20000)
    assert parse_salary("年薪20-30万") == (200000 // 12, 300000 // 12)
    assert parse_salary("面议") == (None, None)
    assert parse_salary(None) == (None, None)


def test_live_formats():
    assert parse_salary("1-2万") == (10000, 20000)
    assert parse_salary("1.2-1.9万") == (12000, 19000)
    assert parse_salary("8千-1万") == (8000, 10000)
    assert parse_salary("8千-1.2万") == (8000, 12000)
    assert parse_salary("3-5万13薪") == (30000, 50000)
    assert parse_salary("1-2万/月·13薪") == (10000, 20000)


def test_unparseable_returns_none():
    assert parse_salary("按天结算") == (None, None)
    assert parse_salary("") == (None, None)
