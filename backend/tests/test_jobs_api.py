from backend.app.models import Company, Job


def test_list_jobs(client):
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 6
    assert len(data["items"]) == 6


def test_filter_jobs(client):
    resp = client.get("/api/jobs", params={"city": "上海"})
    assert resp.json()["total"] == 2
    resp = client.get("/api/jobs", params={"tag": "急招"})
    assert resp.json()["total"] == 1
    resp = client.get("/api/jobs", params={"salary_min": 12000})
    assert resp.json()["total"] == 1
    resp = client.get("/api/jobs", params={"company_id": "c1"})
    assert resp.json()["total"] == 3
    resp = client.get("/api/jobs", params={"keyword": "工程师"})
    assert resp.json()["total"] == 6
    resp = client.get("/api/jobs", params={"keyword": "Python"})
    assert resp.json()["total"] == 1
    resp = client.get("/api/jobs", params={"keyword": "长宁"})
    assert resp.json()["total"] == 1


def test_filter_by_district(client):
    resp = client.get("/api/jobs", params={"district": "长宁区"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["job_id"] == "j1"
    resp = client.get("/api/jobs", params={"district": "不存在的区"})
    assert resp.json()["total"] == 0


def test_filter_by_area(client):
    resp = client.get("/api/jobs", params={"area": "长宁区"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["job_id"] == "j1"
    resp = client.get("/api/jobs", params={"area": "不存在的地区"})
    assert resp.json()["total"] == 0
    resp = client.get("/api/jobs", params={"area": "长宁区", "publish_time_from": "2024-03-02"})
    assert resp.json()["total"] == 0


def test_filter_publish_time_range(client):
    resp = client.get("/api/jobs", params={"publish_time_from": "2024-02-01"})
    assert resp.json()["total"] == 3
    assert {i["job_id"] for i in resp.json()["items"]} == {"j1", "j2", "j5"}
    resp = client.get("/api/jobs", params={"publish_time_to": "2024-02-01"})
    assert {i["job_id"] for i in resp.json()["items"]} == {"j2", "j3", "j4"}
    resp = client.get("/api/jobs", params={"publish_time_from": "2024-01-15", "publish_time_to": "2024-03-01"})
    assert {i["job_id"] for i in resp.json()["items"]} == {"j1", "j2", "j3"}
    resp = client.get("/api/jobs", params={"publish_time_from": "2024-06-02"})
    assert resp.json()["total"] == 0


def test_filter_options(client):
    resp = client.get("/api/jobs/filter-options")
    assert resp.status_code == 200
    data = resp.json()
    assert data["cities"] == ["上海", "北京"]
    assert set(data["districts"]) == {"长宁区", "海淀区"}
    resp = client.get("/api/jobs/filter-options", params={"city": "上海"})
    assert resp.json()["districts"] == ["长宁区"]
    resp = client.get("/api/jobs/filter-options", params={"city": "北京"})
    assert resp.json()["districts"] == ["海淀区"]
    resp = client.get("/api/jobs/filter-options", params={"city": "不存在的城市"})
    assert resp.json()["districts"] == []


def test_sort_by_activity_score(client):
    resp = client.get("/api/jobs", params={"sort": "activity_score:desc"})
    items = resp.json()["items"]
    assert [i["company_activity_score"] for i in items] == [8, 8, 8, 3, 3, -1]
    assert items[-1]["job_id"] == "j6"


def test_sort_by_publish_time(client):
    resp = client.get("/api/jobs", params={"sort": "publish_time:desc"})
    assert [i["job_id"] for i in resp.json()["items"]] == ["j5", "j1", "j2", "j3", "j4", "j6"]
    resp = client.get("/api/jobs", params={"sort": "publish_time:asc"})
    assert [i["job_id"] for i in resp.json()["items"]] == ["j4", "j3", "j2", "j1", "j5", "j6"]


def test_sort_combined(client):
    resp = client.get("/api/jobs", params=[("sort", "activity_score:desc"), ("sort", "publish_time:desc")])
    assert [i["job_id"] for i in resp.json()["items"]] == ["j1", "j2", "j3", "j5", "j4", "j6"]


def test_sort_invalid(client):
    resp = client.get("/api/jobs", params={"sort": "foo:desc"})
    assert resp.status_code == 400
    resp = client.get("/api/jobs", params={"sort": "publish_time"})
    assert resp.status_code == 400
    resp = client.get("/api/jobs", params={"sort": "publish_time:sideways"})
    assert resp.status_code == 400


def test_get_job_detail(client):
    resp = client.get("/api/jobs/j1")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Python工程师"


def test_job_company_fields(client):
    resp = client.get("/api/jobs/j1")
    data = resp.json()
    assert data["company_id"] == "c1"
    assert data["company_name"] == "A公司"
    assert data["company_activity"] == "今日回复8次"
    assert data["company_activity_score"] == 8
    assert data["degree"] == "本科"
    assert data["year"] == "3-4年"
    resp2 = client.get("/api/jobs", params={"sort": "publish_time:desc"})
    first = resp2.json()["items"][0]
    assert first["company_name"] == "B公司"
    assert first["company_activity"] == "3分钟前回复"
    assert first["company_activity_score"] == 3


def test_companies_filter(client):
    resp = client.get("/api/companies", params={"type": "民营"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
