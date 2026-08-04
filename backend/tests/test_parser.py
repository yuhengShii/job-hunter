from pathlib import Path
from datetime import datetime

from backend.app.scrapers.parser import parse_company_page, parse_search_page

FIXTURES = Path(__file__).parent / "fixtures"
SEARCH_HTML = (FIXTURES / "51job_search.html").read_text(encoding="utf-8")
COMPANY_HTML = (FIXTURES / "51job_company.html").read_text(encoding="utf-8")


def test_search_page_parse_first_card():
    result = parse_search_page(SEARCH_HTML, page_num=1)
    assert not result.failed
    assert result.total_pages == 50
    assert len(result.jobs) == 20
    job = result.jobs[0]
    assert job.job_id == "171875192"
    assert "Python" in job.title
    assert job.salary_raw == "1-2万"
    assert job.salary_min == 10000 and job.salary_max == 20000
    assert job.city == "上海" and job.district == "黄浦区"
    assert job.area == "上海·黄浦区"
    assert job.company_id == "2543553"
    assert job.tags == ["五险一金", "餐饮补贴", "带薪年假", "做五休二"]
    assert job.publish_time == datetime(2026, 4, 30, 16, 53, 19)
    assert job.job_url is None


def test_search_page_company_from_card():
    result = parse_search_page(SEARCH_HTML, page_num=1)
    # fixture 实测 20 张卡片仅有 18 个唯一 company_id（2543553 与 2274319 各出现 2 次）
    assert len(result.companies) == 18
    comp = next(c for c in result.companies if c.company_id == "2543553")
    assert comp.name == "立信会计师事务所（特殊普通合伙）"
    assert comp.type == "民营"
    assert comp.industry == "其他专业服务丨财务/审计/税务"
    assert comp.size == "5000-10000人"
    # fixture 卡片 tip 为"简历处理快"（不含"回复"二字，旧逻辑会漏抓）
    assert comp.activity == "简历处理快"


def test_search_page_activity_from_card():
    html = """
    <div class="joblist-item">
      <div class="joblist-item-job" sensorsdata='{"jobId":"A1","jobTitle":"测试","jobSalary":"1-2万","jobArea":"上海-黄浦区","companyId":"C9"}'>
      </div>
      <div class="joblist-item-jobinfo text-cut">
        <span class="sal text-cut">1-2万</span>
        <div class="area"><div class="shrink-0">上海·黄浦区</div></div>
        <span class="tip shrink-0">今日回复8次</span>
      </div>
      <div class="joblist-item-tags"><div class="tags"><div class="tag">五险一金</div></div></div>
      <a class="cname">测试公司</a>
      <div class="bc"><div class="dc">软件</div><div class="dc" title="民营">民营</div><div class="dc">100-499人</div></div>
    </div>
    """
    result = parse_search_page(html, page_num=1)
    assert len(result.companies) == 1
    comp = result.companies[0]
    assert comp.company_id == "C9"
    assert comp.activity == "今日回复8次"


def test_search_page_activity_multiple_tips():
    html = """
    <div class="joblist-item">
      <div class="joblist-item-job" sensorsdata='{"jobId":"A2","jobTitle":"测试","jobSalary":"1-2万","jobArea":"上海-黄浦区","companyId":"C10"}'>
      </div>
      <div class="joblist-item-jobinfo text-cut">
        <span class="sal text-cut">1-2万</span>
        <div class="area"><div class="shrink-0">上海·黄浦区</div></div>
        <span class="tip shrink-0">今日回复10+次</span>
        <span class="tip shrink-0">简历处理快</span>
        <span class="tip shrink-0">喜欢聊天</span>
      </div>
      <div class="joblist-item-tags"><div class="tags"><div class="tag">五险一金</div></div></div>
      <a class="cname">测试公司</a>
      <div class="bc"><div class="dc">软件</div><div class="dc" title="民营">民营</div><div class="dc">100-499人</div></div>
    </div>
    """
    result = parse_search_page(html, page_num=1)
    assert len(result.companies) == 1
    comp = result.companies[0]
    assert comp.activity == "今日回复10+次、简历处理快、喜欢聊天"


def test_search_page_activity_non_reply_tip():
    html = """
    <div class="joblist-item">
      <div class="joblist-item-job" sensorsdata='{"jobId":"A3","jobTitle":"测试","jobSalary":"1-2万","jobArea":"上海-黄浦区","companyId":"C11"}'>
      </div>
      <div class="joblist-item-jobinfo text-cut">
        <span class="sal text-cut">1-2万</span>
        <div class="area"><div class="shrink-0">上海·黄浦区</div></div>
        <span class="tip shrink-0">1天内处理简历</span>
      </div>
      <div class="joblist-item-tags"><div class="tags"><div class="tag">五险一金</div></div></div>
      <a class="cname">测试公司</a>
      <div class="bc"><div class="dc">软件</div><div class="dc" title="民营">民营</div><div class="dc">100-499人</div></div>
    </div>
    """
    result = parse_search_page(html, page_num=1)
    assert len(result.companies) == 1
    comp = result.companies[0]
    assert comp.activity == "1天内处理简历"


def test_search_page_tags_fallback():
    result = parse_search_page(SEARCH_HTML, page_num=1)
    tagged = [j for j in result.jobs if j.tags]
    # fixture 实测 20 张卡片中第 17 张无 tags（jobLabel 与 DOM 均无），其余 19 张有
    assert len(tagged) == 19
    assert tagged[0].tags == ["五险一金", "餐饮补贴", "带薪年假", "做五休二"]


def test_captcha_page_marks_captcha():
    html = '<html><body><div id="aliyunCaptcha-window-embed" class="aliyunCaptcha-show">请按住滑块，拖动到最右边</div></body></html>'
    result = parse_search_page(html, page_num=1)
    assert result.failed is True
    assert result.captcha is True
    assert result.blocked is False


def test_normal_page_not_captcha():
    result = parse_search_page(SEARCH_HTML, page_num=1)
    assert not result.failed
    assert result.captcha is False


def test_waf_page_marks_blocked():
    html = '<html><body>安全验证页面</body></html>'
    result = parse_search_page(html, page_num=1)
    assert result.failed
    assert result.blocked is True
    assert result.jobs == []


def test_normal_page_not_blocked():
    result = parse_search_page(SEARCH_HTML, page_num=1)
    assert not result.failed
    assert result.blocked is False


def test_empty_page_not_blocked():
    html = "<html><body><div class='joblist'>无职位</div></body></html>"
    result = parse_search_page(html, page_num=1)
    assert result.failed is True
    assert result.blocked is False


def test_company_page_synthetic():
    comp = parse_company_page(COMPANY_HTML)
    assert comp is not None
    assert comp.name == "示例科技"
    assert comp.type == "民营"
    assert comp.industry == "计算机软件"
    assert comp.size == "500-1000人"
    assert comp.activity == "30天"


def test_company_page_verification_returns_none():
    assert parse_company_page("<html><body>安全验证</body></html>") is None


def test_search_page_card_with_single_dc_cell():
    html = """
    <div class="joblist-item">
      <div class="joblist-item-job"
           sensorsdata='{"jobId":"1","jobTitle":"测试职位","jobSalary":"1-2万","jobArea":"上海·黄浦区","companyId":"999"}'>
      </div>
      <div class="bc"><div class="dc">计算机软件</div></div>
    </div>
    """
    result = parse_search_page(html, page_num=1)
    assert not result.failed
    assert len(result.jobs) == 1
    assert result.jobs[0].job_id == "1"
    comp = result.companies[0]
    assert comp.type is None
    assert comp.size is None
