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


def test_mixed_unit_lo_below_1_returns_none():
    # 意图锁定：PRD §4 未枚举"0.8-1.2万"这类小数值格式，lo<1 守卫使其记日志并置 NULL
    assert parse_salary("0.8-1.2万") == (None, None)
    assert parse_salary("0.5-1万") == (None, None)
