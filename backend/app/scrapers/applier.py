"""一键投递：从 51job 新版搜索页（we.51job.com）投递职位。

背景（实测 2026-08）：职位详情页（jobs.51job.com）有独立的阿里云滑块风控，
Playwright 浏览器（含真实 Chrome、有头手动拖动）均被识别为自动化而拒绝；
而搜索页（we.51job.com）风控宽松，职位卡片自带「投递」按钮，投递弹窗
（简历选择/附件/成功提示）都在同一 SPA 内完成。故投递流程改为：
搜索职位标题 → 按 jobId 定位卡片 → 点「投递」→ 处理弹窗序列 → 判成功。

选择器/文案随站点改版集中在本文件维护；本模块不管理浏览器生命周期，
只针对一个已打开的 Page 做「搜索→定位→点击→弹窗处理」，便于用假 page 单测。
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
_APPLY_BTN_SELECTOR = ".btn.apply"
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
_CITY_TEXTS = ("选择城市",)
_RESUME_TEXTS = ("选择需要投递的简历", "选择投递简历")
_ATTACH_TEXTS = ("附件简历", "同步发送")
_CAPTCHA_MARKERS = ("请按住滑块", "aliyunCaptcha", "安全验证")

# ---- 页面 JS 片段（fake page 单测时按其中特征串分发） ----
_FIND_CARD_JS = """(jobId) => {
    const cards = Array.from(document.querySelectorAll('.joblist-item'));
    for (let i = 0; i < cards.length; i++) {
        const el = cards[i].querySelector('.joblist-item-job');
        const sd = el ? el.getAttribute('sensorsdata') : null;
        if (!sd) continue;
        try {
            if (String(JSON.parse(sd).jobId) === String(jobId)) return i;
        } catch (e) { /* 忽略坏 JSON */ }
    }
    return -1;
}"""

_CARD_TEXT_JS = """(jobId) => {
    const cards = Array.from(document.querySelectorAll('.joblist-item'));
    for (const c of cards) {
        const el = c.querySelector('.joblist-item-job');
        const sd = el ? el.getAttribute('sensorsdata') : null;
        if (!sd) continue;
        try {
            if (String(JSON.parse(sd).jobId) === String(jobId)) return (c.innerText || '').slice(0, 200);
        } catch (e) { /* 忽略坏 JSON */ }
    }
    return '';
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

async def _body_text(page) -> str:
    try:
        text = await page.evaluate(_BODY_TEXT_JS)
        return text or ""
    except Exception:
        return ""


async def _find_card_index(page, job_id: str) -> int:
    try:
        return int(await page.evaluate(_FIND_CARD_JS, job_id))
    except Exception:
        return -1


async def _card_text(page, job_id: str) -> str:
    try:
        return str(await page.evaluate(_CARD_TEXT_JS, job_id) or "")
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


async def _click_card_apply(page, index: int) -> bool:
    try:
        btn = page.locator(_CARD_SELECTOR).nth(index).locator(_APPLY_BTN_SELECTOR).first
        await btn.click(timeout=8000)
        return True
    except Exception:
        return False


# ---- 主流程 ----

async def apply_to_job(
    page, target: ApplyTarget, goto_timeout: int = 60000, manual_wait: float = 0.0
) -> ApplyResult:
    """从搜索页对单个职位执行投递。返回 (status, message)，不抛出。

    manual_wait > 0 表示有头人工模式：搜索页遇滑块时跳过自动拖动，
    等待人工拖动通过（最多 manual_wait 秒）。
    """
    keyword = _search_keyword(target.title)
    area = _CITY_CODE.get(target.city or "", "000000")
    page_num = 1
    checked = 0
    index = -1
    while page_num <= _MAX_SEARCH_PAGES:
        if page_num == 1:
            url = build_search_url(keyword, 1, area)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=goto_timeout)
            except Exception as exc:
                return ApplyResult(target.job_id, "failed", f"页面打开失败：{exc}")
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
                    return ApplyResult(target.job_id, "captcha", "验证码未通过")
                try:
                    await page.wait_for_selector(_CARD_SELECTOR, timeout=30000)
                except Exception:
                    return ApplyResult(target.job_id, "failed", "搜索结果未加载")
            else:
                return ApplyResult(target.job_id, "failed", "搜索结果未加载")
        checked += 1
        index = await _find_card_index(page, target.job_id)
        if index >= 0:
            break
        page_num += 1
    if index < 0:
        return ApplyResult(
            target.job_id, "failed", f"搜索结果前 {checked} 页未找到该职位（可能已下架）"
        )
    card_text = await _card_text(page, target.job_id)
    if any(m in card_text for m in _DONE_TEXTS):
        return ApplyResult(target.job_id, "skipped", "已投递")
    if not await _click_card_apply(page, index):
        return ApplyResult(target.job_id, "failed", "未找到投递按钮")
    await page.wait_for_timeout(2500)

    return await _handle_dialogs(page, target)


async def _handle_dialogs(page, target: ApplyTarget) -> ApplyResult:
    for _ in range(6):
        dialog = await _visible_dialog(page)
        if dialog is None:
            # 无可见弹窗：看目标卡片是否已变为「已投递」
            card_text = await _card_text(page, target.job_id)
            if any(m in card_text for m in _DONE_TEXTS) or any(
                m in card_text for m in _SUCCESS_TEXTS
            ):
                return ApplyResult(target.job_id, "success", "投递成功")
            await page.wait_for_timeout(2000)
            dialog = await _visible_dialog(page)
            if dialog is None:
                return ApplyResult(target.job_id, "failed", "投递流程未出现弹窗")
        text = dialog.get("text", "")
        if any(m in text for m in _SUCCESS_TEXTS):
            return ApplyResult(target.job_id, "success", "投递成功")
        if any(m in text for m in _HINT_TEXTS):
            # 简历不完整提示：优先「仍要投递/继续投递」，否则关闭后重试
            if not await _click_dialog_button(page, ("仍要投递", "继续投递", "仍然投递")):
                await _close_dialog(page)
            continue
        if any(m in text for m in _CITY_TEXTS):
            # 多城市投递：点目标城市（或第一个可选项）再确定
            clicked = None
            if target.city:
                clicked = await _click_dialog_button(page, (target.city,))
            if clicked is None:
                clicked = await _click_dialog_button(page, ("不限", "全国"))
            if clicked is None:
                await _close_dialog(page)
            else:
                await _click_dialog_button(page, ("确定", "确认"))
            continue
        if any(m in text for m in _RESUME_TEXTS):
            await _click_resume_item(page)  # 点第一份简历（best-effort）
            clicked = await _click_dialog_button(page, ("立即申请", "立即投递"))
            if clicked is None:
                return ApplyResult(target.job_id, "failed", f"简历弹窗未找到申请按钮：{text[:60]}")
            continue
        if any(m in text for m in _ATTACH_TEXTS):
            if await _click_dialog_button(page, ("发送", "确定")):
                continue
        return ApplyResult(target.job_id, "failed", f"弹窗异常：{text[:80]}")
    return ApplyResult(target.job_id, "failed", "投递流程超时")
