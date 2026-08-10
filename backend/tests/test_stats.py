from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from backend.app.api.deps import ensure_admin
from backend.app.core.database import SessionLocal, init_db
from backend.app.main import create_app
from backend.app.models import Company, Job, Keyword, ScrapeTask, TaskStatus
from backend.app.services.stats import (
    get_window_start,
    overview,
    salary_stats,
    tag_stats,
    distribution_stats,
    trend_stats,
)


def _seed(config):
    init_db(config)
    with SessionLocal() as s:
        ensure_admin(s, config)
        kw = Keyword(keyword="python")
        s.add(kw)
        s.commit()
        base = datetime(2026, 7, 1, 10, 0, 0)
        s.add(ScrapeTask(keyword_id=kw.id, status=TaskStatus.SUCCESS.value, start_time=base, end_time=base + timedelta(minutes=5)))
        old = datetime(2026, 6, 1, 10, 0, 0)
        s.add(ScrapeTask(keyword_id=kw.id, status=TaskStatus.SUCCESS.value, start_time=old, end_time=old + timedelta(minutes=5)))
        s.add_all([
            Company(company_id="c1", name="A", type="民营", industry="软件", size="100人"),
            Company(company_id="c2", name="B", type="国企", industry="金融", size="1000人"),
        ])
        s.add_all([
            Job(job_id="j1", title="t1", salary_min=8000, salary_max=12000, city="上海", tags=["急招"], company_id="c1", updated_at=base + timedelta(hours=1)),
            Job(job_id="j2", title="t2", salary_min=15000, salary_max=25000, city="北京", tags=["高薪"], company_id="c2", updated_at=base + timedelta(hours=2)),
            Job(job_id="j3", title="t3", salary_min=9000, salary_max=15000, city="上海", tags=["急招", "双休"], company_id="c1", updated_at=old + timedelta(hours=1)),
        ])
        s.commit()


def test_window_uses_latest_success_task(config):
    _seed(config)
    with SessionLocal() as s:
        window = get_window_start(s)
        assert window == datetime(2026, 7, 1, 10, 0, 0)
        stats = overview(s, window)
        assert stats["total_jobs"] == 2
        assert stats["total_cities"] == 2
        assert stats["total_companies"] == 2
        assert stats["salary_parsed"] == 2


def test_tag_stats_window(config):
    _seed(config)
    with SessionLocal() as s:
        tags = tag_stats(s, get_window_start(s), top_n=2)
        assert [t["tag"] for t in tags] == ["急招", "高薪"]


def test_stats_api_endpoints(config):
    _seed(config)
    app = create_app(config)
    with TestClient(app) as c:
        token = c.post("/api/auth/login", json={"username": config.auth_username, "password": config.auth_password}).json()["access_token"]
        c.headers.update({"Authorization": f"Bearer {token}"})
        for ep in ["overview", "salary", "company", "trend", "tags"]:
            resp = c.get(f"/api/stats/{ep}")
            assert resp.status_code == 200


def test_distribution_by_city(config):
    _seed(config)
    with SessionLocal() as s:
        window = get_window_start(s)
        res = distribution_stats(s, window)
        by_key = {i["key"]: i["count"] for i in res["items"]}
        assert res["group_by"] == "city"
        assert by_key == {"上海": 1, "北京": 1}


def test_salary_median_even_sample(config):
    _seed(config)
    with SessionLocal() as s:
        window = get_window_start(s)
        base = datetime.now()
        s.add(Job(job_id="m1", title="t", salary_min=10000, salary_max=10000, city="测试城", updated_at=base))
        s.add(Job(job_id="m2", title="t", salary_min=30000, salary_max=30000, city="测试城", updated_at=base))
        s.add(Job(job_id="m3", title="t", salary_min=50000, salary_max=50000, city="测试城", updated_at=base))
        s.add(Job(job_id="m4", title="t", salary_min=70000, salary_max=70000, city="测试城", updated_at=base))
        s.commit()
        res = salary_stats(s, window - timedelta(days=1), group_by="city")
        item = next(i for i in res["items"] if i["key"] == "测试城")
        # 4 个样本：中位数 = (30000+50000)/2
        assert item["count"] == 4
        assert item["median"] == 40000


def test_distribution_window_filter(config):
    _seed(config)
    with SessionLocal() as s:
        window = get_window_start(s)
        old = window - timedelta(days=30)
        s.add(Job(job_id="w1", title="t", city="广州", updated_at=old))
        s.commit()
        res = distribution_stats(s, window)
        keys = [i["key"] for i in res["items"]]
        assert "广州" not in keys
        assert set(keys) == {"上海", "北京"}


def test_distribution_by_district(config):
    _seed(config)
    with SessionLocal() as s:
        base = get_window_start(s)
        s.add(Job(job_id="d1", title="t", city="上海", district="浦东新区", updated_at=base + timedelta(hours=5)))
        s.add(Job(job_id="d2", title="t", city="上海", district="闵行区", updated_at=base + timedelta(hours=6)))
        s.add(Job(job_id="d3", title="t", city="北京", district="海淀区", updated_at=base + timedelta(hours=7)))
        s.commit()
        res = distribution_stats(s, base, group_by="district")
        by_key = {i["key"]: i["count"] for i in res["items"]}
        assert res["group_by"] == "district"
        assert by_key == {"未知": 2, "浦东新区": 1, "闵行区": 1, "海淀区": 1}  # j1/j2 无 district -> 未知
        counts = [i["count"] for i in res["items"]]
        assert counts == sorted(counts, reverse=True)


def test_distribution_by_area(config):
    _seed(config)
    with SessionLocal() as s:
        base = get_window_start(s)
        s.add(Job(job_id="a1", title="t", city="上海", area="上海-长宁区", updated_at=base + timedelta(hours=5)))
        s.add(Job(job_id="a2", title="t", city="上海", area="上海-浦东新区", updated_at=base + timedelta(hours=6)))
        s.add(Job(job_id="a3", title="t", city="北京", area="北京-海淀区", updated_at=base + timedelta(hours=7)))
        s.commit()
        res = distribution_stats(s, base, group_by="area")
        by_key = {i["key"]: i["count"] for i in res["items"]}
        assert res["group_by"] == "area"
        assert by_key == {"未知": 2, "上海-长宁区": 1, "上海-浦东新区": 1, "北京-海淀区": 1}


def test_distribution_api(config):
    _seed(config)
    app = create_app(config)
    with TestClient(app) as c:
        token = c.post("/api/auth/login", json={"username": config.auth_username, "password": config.auth_password}).json()["access_token"]
        c.headers.update({"Authorization": f"Bearer {token}"})
        resp = c.get("/api/stats/distribution")
        assert resp.status_code == 200
        data = resp.json()
        assert data["group_by"] == "city" and "items" in data
        assert {i["key"] for i in data["items"]} == {"上海", "北京"}
        resp2 = c.get("/api/stats/distribution", params={"group_by": "district"})
        assert resp2.json()["group_by"] == "district"


def test_distribution_api_requires_auth(config):
    _seed(config)
    app = create_app(config)
    with TestClient(app) as c:
        resp = c.get("/api/stats/distribution")
        assert resp.status_code == 401


def test_trend_ungrouped_preserves_format(config):
    _seed(config)
    with SessionLocal() as s:
        window = get_window_start(s)
        res = trend_stats(s, window)
        assert res["group_by"] is None
        assert "days" in res and "series" not in res
        assert sum(d["count"] for d in res["days"]) == 2  # j1/j2 在窗口内


def test_trend_grouped_by_city(config):
    _seed(config)
    with SessionLocal() as s:
        window = get_window_start(s)
        res = trend_stats(s, window, group_by="city")
        assert res["group_by"] == "city"
        by_key = {s2["key"]: s2["points"] for s2 in res["series"]}
        assert set(by_key) == {"上海", "北京"}
        dates = [p["date"] for p in by_key["上海"]]
        assert dates == sorted(dates)
        assert sum(p["count"] for p in by_key["上海"]) == 1  # j1；j3 窗口外
        assert sum(p["count"] for p in by_key["北京"]) == 1  # j2


def test_trend_grouped_fills_missing_dates_with_zero(config):
    _seed(config)
    with SessionLocal() as s:
        window = get_window_start(s)
        old_day = (window - timedelta(days=5)).date().isoformat()
        new_day = (window + timedelta(days=1)).date().isoformat()
        s.add(Job(job_id="t1", title="t", city="上海", updated_at=window - timedelta(days=5)))
        s.add(Job(job_id="t2", title="t", city="北京", updated_at=window + timedelta(days=1)))
        s.commit()
        res = trend_stats(s, window - timedelta(days=10), group_by="city")
        by_key = {s2["key"]: s2["points"] for s2 in res["series"]}
        # 两个城市的日期序列完全一致（缺失补 0）
        assert [p["date"] for p in by_key["上海"]] == [p["date"] for p in by_key["北京"]]
        sh = {p["date"]: p["count"] for p in by_key["上海"]}
        bj = {p["date"]: p["count"] for p in by_key["北京"]}
        assert sh[old_day] == 1 and bj[old_day] == 0
        assert bj[new_day] == 1 and sh[new_day] == 0


def test_trend_grouped_unknown_fallback(config):
    _seed(config)
    with SessionLocal() as s:
        window = get_window_start(s)
        res = trend_stats(s, window, group_by="district")
        by_key = {s2["key"]: s2["points"] for s2 in res["series"]}
        assert set(by_key) == {"未知"}  # j1/j2 均无 district
        assert sum(p["count"] for p in by_key["未知"]) == 2


def test_trend_uses_publish_time_when_present(config):
    _seed(config)
    with SessionLocal() as s:
        window = get_window_start(s)
        s.add(Job(job_id="pt1", title="t", city="上海", updated_at=window + timedelta(hours=2),
                  publish_time=window - timedelta(days=3)))
        s.commit()
        res = trend_stats(s, window)
        by_day = {d["date"]: d["count"] for d in res["days"]}
        # pt1 按 publish_time（3 天前）而非 updated_at（今天）归组
        assert by_day.get((window - timedelta(days=3)).date().isoformat(), 0) == 1
        # j1/j2 无 publish_time，回落 updated_at（当天）
        assert by_day.get(window.date().isoformat(), 0) == 2


def test_trend_api_group_by(config):
    _seed(config)
    app = create_app(config)
    with TestClient(app) as c:
        token = c.post("/api/auth/login", json={"username": config.auth_username, "password": config.auth_password}).json()["access_token"]
        c.headers.update({"Authorization": f"Bearer {token}"})
        resp = c.get("/api/stats/trend")
        assert resp.status_code == 200
        assert resp.json()["group_by"] is None
        resp2 = c.get("/api/stats/trend", params={"group_by": "city"})
        data2 = resp2.json()
        assert data2["group_by"] == "city"
        assert {s["key"] for s in data2["series"]} == {"上海", "北京"}
