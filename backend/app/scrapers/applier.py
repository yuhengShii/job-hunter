"""一键投递：在 51job 新版搜索页（we.51job.com）批量投递职位。

背景（实测 2026-08）：
- 职位详情页（jobs.51job.com）有独立阿里云滑块风控，Playwright 浏览器（含真实
  Chrome、有头手动拖动）均被识别为自动化而拒绝；
- 搜索页（we.51job.com）风控宽松，职位卡片自带「投递」按钮，且支持「勾选 +
  一键投递」批量模式：勾选多张卡片后点工具栏 button.p_but.all_apply，页面
  JS 会一次发送一个带合法签名的 light-apply-job 请求（applyJobList 含全部
  选中 jobId），直接「投递成功！」。
- 投递接口为 cupid.51job.com/open/user-apply/.../light-apply-job，但每个请求
  带由阿里云接口保护 SDK 计算的 sign 签名头，Python 端无法复刻，故必须通过
  页面 UI（勾选 + 一键投递）让页面代为签名。

本模块按「搜索关键词」分组：每个关键词只搜索一次（自动翻页），把该词下所有
目标职位勾选后一键投递。选择器/文案随站点改版集中在本文件维护。
"""

import logging
import re
from dataclasses import dataclass
from urllib.parse import quote

from backend.app.scrapers.captcha import solve_aliyun_captcha, wait_aliyun_manual

logger = logging.getLogger("job_hunter")

_SEARCH_URL = (
    "https://we.51job.com/pc/search?keyword={kw}&searchType=2&sortType=0&pageNum={n}&jobArea={area}"
)
_CARD_SELECTOR = ".joblist-item"
_BATCH_APPLY_SELECTOR = "button.p_but.all_apply, .p_but.all_apply"
_MAX_SEARCH_PAGES = 4

# 已知城市编码（与前端 utils/cities.ts 一致），其余城市回退全国搜索
_CITY_CODE = {
    "北京": "010000",
    "上海": "020000",
    "广州": "030200",
    "深圳": "040000",
    "杭州": "080200",
    "郑州": "170200",
}

# 标题搜索词净化：去掉括号后缀与「--」「 - 」后的部分（如 "项目运作实习生 （上海）"→"项目运作实习生"）
_STRIP_SUFFIX_RE = re.compile(r"[（(][^）)]*[)）]|--.*$| - .*$")

# 弹窗/状态文案（best-effort，实测后按需增补）
_DONE_TEXTS = ("已投递", "已申请")
_SUCCESS_TEXTS = ("投递成功", "申请成功", "投递已提交", "简历投递成功")
_HINT_TEXTS = ("工作经验不完整", "简历不完整", "完善后再投递")
_RESUME_TEXTS = ("选择需要投递的简历", "选择投递简历")
_ATTACH_TEXTS = ("附件简历", "同步发送")
_CAPTCHA_MARKERS = ("请按住滑块", "aliyunCaptcha", "安全验证")
# 51job 每日投递上限提示（社区项目实测文案，见 vvvsrx/get_jobs）
_DAILY_LIMIT_TEXTS = (
    "今日投递太多",
    "今日投递已达上限",
    "投递次数已达上限",
    "投递已达上限",
    "达到上限",
    "超出限制",
    "休息一下明天再来",
)

# ---- 页面 JS 片段（fake page 单测时按其中特征串分发） ----

_SELECT_CARDS_JS = """(jobIds) => {
    const selected = [];
    const skipped = [];
    const cards = Array.from(document.querySelectorAll('.joblist-item'));
    for (const c of cards) {
        const el = c.querySelector('.joblist-item-job');
        const sd = el ? el.getAttribute('sensorsdata') : null;
        if (!sd) continue;
        let jobId = null;
        try { jobId = String(JSON.parse(sd).jobId); } catch (e) { continue; }
        if (!jobIds.includes(jobId)) continue;
        if ((c.innerText || '').includes('已投递')) { skipped.push(jobId); continue; }
        const ick = c.querySelector('.ick');
        if (ick && !ick.className.includes('sel-yes')) {
            ick.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
        }
        selected.push(jobId);
    }
    return { selected, skipped };
}"""

_DIALOG_INFO_JS = """() => {
    const d = Array.from(document.querySelectorAll('.el-dialog')).find(
        x => x.offsetWidth > 0 && x.style.display !== 'none'
    );
    if (!d) return null;
    return {
        text: (d.innerText || '').slice(0, 300),
        buttons: Array.from(d.querySelectorAll('button, .btn, [role=button]')).map(b => ({
            text: (b.innerText || '').trim().slice(0, 16)
        })).filter(x => x.text)
    };
}"""

_CLICK_DIALOG_BTN_JS = """(texts) => {
    const d = Array.from(document.querySelectorAll('.el-dialog')).find(x => x.offsetWidth > 0);
    if (!d) return null;
    const re = new RegExp(texts.join('|'));
    const els = Array.from(d.querySelectorAll('button, .btn, [role=button], a, p, span, li'));
    const t = els.find(e => {
        const txt = (e.innerText || '').trim();
        return txt && txt.length < 30 && re.test(txt) && e.offsetWidth > 0;
    });
    if (t) { t.click(); return (t.innerText || '').trim(); }
    return null;
}"""

_CLICK_RESUME_ITEM_JS = """() => {
    const d = Array.from(document.querySelectorAll('.el-dialog')).find(
        x => x.offsetWidth > 0 && (x.innerText || '').includes('选择需要投递的简历')
    );
    if (!d) return false;
    const item = d.querySelector('.attachment_item, .pc-apply-resume__select, .resume-item, .radio, li');
    if (item) { item.click(); return true; }
    return false;
}"""

_CLOSE_DIALOG_JS = """() => {
    const d = Array.from(document.querySelectorAll('.el-dialog')).find(x => x.offsetWidth > 0);
    if (!d) return false;
    const x = d.querySelector('.el-dialog__headerbtn');
    if (x) { x.click(); return true; }
    return false;
}"""

_BODY_TEXT_JS = "document.body ? document.body.innerText : ''"


@dataclass
class ApplyTarget:
    job_id: str
    title: str
    job_url: str | None = None
    city: str | None = None


@dataclass
class ApplyResult:
    job_id: str
    status: str  # success | failed | skipped | captcha(内部信号，由 apply_to_jobs 兜底)
    message: str = ""


def build_job_url(target: ApplyTarget) -> str:
    return target.job_url or f"https://jobs.51job.com/all/{target.job_id}.html"


def build_search_url(keyword: str, page_num: int = 1, area: str = "000000") -> str:
    return _SEARCH_URL.format(kw=quote(keyword), n=page_num, area=area)


def _search_keyword(title: str) -> str:
    """从职位标题生成搜索关键词（去掉括号后缀与分隔符后缀）。"""
    kw = _STRIP_SUFFIX_RE.sub("", title or "").strip()
    return kw or (title or "").strip()


# ---- 页面操作 helper（可被测试 monkeypatch） ----

async def _body_text(page) -> str:
    try:
        text = await page.evaluate(_BODY_TEXT_JS)
        return text or ""
    except Exception:
        return ""


async def _visible_dialog(page) -> dict | None:
    try:
        return await page.evaluate(_DIALOG_INFO_JS)
    except Exception:
        return None


async def _click_dialog_button(page, texts: tuple[str, ...]) -> str | None:
    try:
        return await page.evaluate(_CLICK_DIALOG_BTN_JS, list(texts))
    except Exception:
        return None


async def _click_resume_item(page) -> bool:
    try:
        return bool(await page.evaluate(_CLICK_RESUME_ITEM_JS))
    except Exception:
        return False


async def _close_dialog(page) -> bool:
    try:
        return bool(await page.evaluate(_CLOSE_DIALOG_JS))
    except Exception:
        return False


async def _click_next_page(page, target_page: int) -> bool:
    """点击分页器下一页并等待新页激活（与搜索抓取同款逻辑）。"""
    try:
        next_btn = page.locator(".el-pagination .btn-next, .el-pager .btn-next").first
        await next_btn.click(timeout=10000)
        await page.wait_for_function(
            f"document.querySelector('.el-pager li.number.active')?.textContent.trim() === '{target_page}'",
            timeout=15000,
        )
        await page.wait_for_timeout(800)
        return True
    except Exception:
        return False


async def _select_cards(page, job_ids: list[str]) -> dict:
    """在搜索结果中勾选目标职位卡片。返回 {selected: [jobId], skipped: [已投递的jobId]}。"""
    try:
        return await page.evaluate(_SELECT_CARDS_JS, job_ids) or {"selected": [], "skipped": []}
    except Exception:
        return {"selected": [], "skipped": []}


async def _click_batch_apply(page) -> bool:
    """点击工具栏「一键投递」。"""
    try:
        btn = page.locator(_BATCH_APPLY_SELECTOR).first
        await btn.click(timeout=8000)
        return True
    except Exception:
        return False


def _mark_all(results: dict, status: str, message: str) -> dict:
    for job_id, r in results.items():
        if r is None:
            results[job_id] = ApplyResult(job_id, status, message)
    return results


# ---- 批量弹窗处理 ----

async def _batch_dialog(page) -> ApplyResult:
    """处理「一键投递」后的弹窗序列，返回一个仅携带 status/message 的结果。"""
    for _ in range(6):
        dialog = await _visible_dialog(page)
        if dialog is None:
            await page.wait_for_timeout(2000)
            dialog = await _visible_dialog(page)
            if dialog is None:
                return ApplyResult("", "failed", "投递流程未出现弹窗")
        text = dialog.get("text", "")
        if any(m in text for m in _SUCCESS_TEXTS):
            await _close_dialog(page)  # 关闭成功弹窗，继续下一批
            return ApplyResult("", "success", "投递成功")
        if any(m in text for m in _DAILY_LIMIT_TEXTS):
            return ApplyResult("", "failed", "今日投递已达上限（51job 每日限制）")
        if any(m in text for m in _HINT_TEXTS):
            if not await _click_dialog_button(page, ("仍要投递", "继续投递", "仍然投递")):
                await _close_dialog(page)
            continue
        if any(m in text for m in _RESUME_TEXTS):
            await _click_resume_item(page)
            if await _click_dialog_button(page, ("立即申请", "立即投递")):
                continue
            return ApplyResult("", "failed", f"简历弹窗未找到申请按钮：{text[:60]}")
        if any(m in text for m in _ATTACH_TEXTS):
            if await _click_dialog_button(page, ("发送", "确定")):
                continue
        return ApplyResult("", "failed", f"弹窗异常：{text[:80]}")
    return ApplyResult("", "failed", "投递流程超时")


# ---- 主流程 ----

async def apply_job_group(page, targets: list[ApplyTarget], manual_wait: float = 0.0) -> dict:
    """在同一搜索页上批量投递一组同关键词职位。返回 {job_id: ApplyResult}。

    manual_wait > 0 表示有头人工模式：搜索页遇滑块时跳过自动拖动，
    等待人工拖动通过（最多 manual_wait 秒）。
    """
    results: dict[str, ApplyResult | None] = {t.job_id: None for t in targets}
    keyword = _search_keyword(targets[0].title)
    area = _CITY_CODE.get(targets[0].city or "", "000000")
    page_num = 1
    checked = 0
    pending = list(targets)
    while page_num <= _MAX_SEARCH_PAGES and pending:
        if page_num == 1:
            url = build_search_url(keyword, 1, area)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception as exc:
                return _mark_all(results, "failed", f"页面打开失败：{exc}")
        else:
            if not await _click_next_page(page, page_num):
                break
        try:
            await page.wait_for_selector(_CARD_SELECTOR, timeout=30000)
        except Exception:
            text = await _body_text(page)
            if any(m in text for m in _CAPTCHA_MARKERS):
                if manual_wait > 0:
                    solved = await wait_aliyun_manual(page, timeout=manual_wait)
                else:
                    try:
                        solved = await solve_aliyun_captcha(page)
                    except Exception:
                        solved = False
                if not solved:
                    return _mark_all(results, "captcha", "验证码未通过")
                try:
                    await page.wait_for_selector(_CARD_SELECTOR, timeout=30000)
                except Exception:
                    return _mark_all(results, "failed", "搜索结果未加载")
            else:
                return _mark_all(results, "failed", "搜索结果未加载")
        checked += 1
        on_page = [t for t in pending if results[t.job_id] is None]
        if on_page:
            pick = await _select_cards(page, [t.job_id for t in on_page])
            for job_id in pick.get("skipped", []):
                results[job_id] = ApplyResult(job_id, "skipped", "已投递")
            if pick.get("selected"):
                await page.wait_for_timeout(800)
                if await _click_batch_apply(page):
                    outcome = await _batch_dialog(page)
                    for job_id in pick["selected"]:
                        results[job_id] = ApplyResult(job_id, outcome.status, outcome.message)
                else:
                    for job_id in pick["selected"]:
                        results[job_id] = ApplyResult(job_id, "failed", "未找到一键投递按钮")
        pending = [t for t in pending if results[t.job_id] is None]
        page_num += 1
    for t in pending:
        if results[t.job_id] is None:
            results[t.job_id] = ApplyResult(
                t.job_id, "failed", f"搜索结果前 {checked} 页未找到该职位（可能已下架）"
            )
    return results


async def apply_to_job(
    page, target: ApplyTarget, goto_timeout: int = 60000, manual_wait: float = 0.0
) -> ApplyResult:
    """单职位投递（apply_job_group 的单元素版本，保留兼容）。"""
    results = await apply_job_group(page, [target], manual_wait=manual_wait)
    return results.get(target.job_id) or ApplyResult(target.job_id, "failed", "未知错误")
