import json
import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from backend.app.scrapers.base import CompanyDraft, JobDraft, PageResult
from backend.app.services.salary import parse_salary

logger = logging.getLogger("job_hunter")

_JOB_TIME_FMT = "%Y-%m-%d %H:%M:%S"
_VERIFY_MARKERS = ("安全验证", "验证码", "renderData")
_CAPTCHA_MARKERS = ("aliyunCaptcha", "请按住滑块")
_TYPE_MAP = {
    "民营": "民营", "国企": "国企", "外企": "外企", "外资企业": "外企",
    "合资": "合资", "上市公司": "上市公司", "事业单位": "事业单位",
    "外资(欧美)": "外企", "外资(非欧美)": "外企",
}


def _is_verification(html: str) -> bool:
    return any(m in html for m in _VERIFY_MARKERS)


def _is_captcha(html: str) -> bool:
    return any(m in html for m in _CAPTCHA_MARKERS)


def _split_area(area: str) -> tuple[str | None, str | None]:
    if not area:
        return None, None
    if "-" in area:
        city, district = area.split("-", 1)
        return city.strip(), district.strip() or None
    if "·" in area:
        city, district = area.split("·", 1)
        return city.strip(), district.strip() or None
    return area.strip(), None


def _parse_job_time(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.strptime(text.strip(), _JOB_TIME_FMT)
    except ValueError:
        return None


def _extract_sensors(el) -> dict:
    raw = el.get("sensorsdata") if el else None
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        logger.warning("sensorsdata JSON 解析失败")
        return {}


def _parse_company_from_card(card, sdata: dict) -> CompanyDraft | None:
    company_id = sdata.get("companyId")
    if not company_id:
        logo = card.select_one(".comlogo")
        m = re.search(r"/CompLogo/\d+/\d+/(\d+)_", logo.get("src", "")) if logo else None
        if m:
            company_id = m.group(1)
    if not company_id:
        return None
    name_el = card.select_one(".cname")
    name = name_el.get_text(strip=True) if name_el else None
    dcs = [el for el in card.select(".bc .dc")]
    industry = dcs[0].get_text(strip=True) if len(dcs) > 0 else None
    if len(dcs) > 1:
        type_raw = dcs[1].get("title") or dcs[1].get_text(strip=True)
    else:
        type_raw = None
    size = dcs[2].get_text(strip=True) if len(dcs) > 2 else None
    return CompanyDraft(
        company_id=company_id,
        name=name,
        type=_TYPE_MAP.get(type_raw or "", type_raw) if type_raw else None,
        industry=industry,
        size=size,
    )


def parse_search_page(html: str, page_num: int) -> PageResult:
    if _is_captcha(html):
        return PageResult(page_num=page_num, jobs=[], failed=True, captcha=True)
    if _is_verification(html):
        return PageResult(page_num=page_num, jobs=[], failed=True, blocked=True)
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(".joblist-item")
    if not cards:
        return PageResult(page_num=page_num, jobs=[], failed=True)
    jobs: list[JobDraft] = []
    companies: list[CompanyDraft] = []
    seen_company: set[str] = set()
    for card in cards:
        el = card.select_one(".joblist-item-job")
        sdata = _extract_sensors(el)
        job_id = sdata.get("jobId")
        if not job_id:
            logger.warning("卡片缺少 jobId，跳过")
            continue
        title = sdata.get("jobTitle") or (
            card.select_one(".jname").get_text(strip=True) if card.select_one(".jname") else ""
        )
        salary_raw = sdata.get("jobSalary") or (
            card.select_one(".sal").get_text(strip=True) if card.select_one(".sal") else None
        )
        salary_min, salary_max = parse_salary(salary_raw)
        area = sdata.get("jobArea") or (
            card.select_one(".area").get_text(strip=True) if card.select_one(".area") else None
        )
        city, district = _split_area(area)
        tags_raw = sdata.get("jobLabel")
        if not tags_raw:
            tags = [t.get_text(strip=True) for t in card.select(".joblist-item-tags .tag")]
        else:
            tags = list(tags_raw) if isinstance(tags_raw, list) else [tags_raw]
        tags = [t for t in tags if t]
        publish_time = _parse_job_time(sdata.get("jobTime"))
        company_id = sdata.get("companyId")
        jobs.append(
            JobDraft(
                job_id=job_id,
                title=title,
                salary_raw=salary_raw,
                salary_min=salary_min,
                salary_max=salary_max,
                city=city,
                district=district,
                area=area,
                tags=tags,
                publish_time=publish_time,
                company_id=company_id,
                job_url=None,
            )
        )
        comp = _parse_company_from_card(card, sdata)
        if comp and comp.company_id not in seen_company:
            seen_company.add(comp.company_id)
            companies.append(comp)
    total_pages = None
    pager_nums = soup.select(".el-pager li.number")
    if pager_nums:
        try:
            total_pages = int(pager_nums[-1].get_text(strip=True))
        except ValueError:
            total_pages = None
    return PageResult(page_num=page_num, jobs=jobs, companies=companies, total_pages=total_pages)


def parse_company_page(html: str) -> CompanyDraft | None:
    if _is_verification(html):
        return None
    soup = BeautifulSoup(html, "html.parser")
    info = soup.select_one(".company-info")
    if not info:
        return None
    name_el = info.select_one("h1")
    pairs: dict[str, str] = {}
    for t1, t2 in zip(info.select(".t1"), info.select(".t2")):
        pairs[t1.get_text(strip=True)] = t2.get_text(strip=True)
    return CompanyDraft(
        company_id="",
        name=name_el.get_text(strip=True) if name_el else None,
        type=pairs.get("公司类型"),
        industry=pairs.get("所属行业"),
        size=pairs.get("公司规模"),
        activity=pairs.get("活跃天数"),
    )
