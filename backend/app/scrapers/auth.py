import logging

from playwright.async_api import Page

from backend.app.scrapers.captcha import (
    detect_geetest,
    solve_aliyun_captcha,
    wait_geetest_manual,
)

logger = logging.getLogger("job_hunter")

_LOGIN_URL = "https://login.51job.com/login.php?lang=c"
# 实测（2026-08）：登录页默认「手机号 + 短信验证码」模式，需先点「密码登录」tab 才出现密码框；
# 提交前需点击协议同意 label（#isread 隐藏 checkbox）；提交按钮为 div#SmsLoginBtn
_USER_INPUT = "#loginname"
_PASS_INPUT = "#password"
_PASSWORD_TAB = "span.loginway"
_AGREE_LABEL = "label"
_SUBMIT = "#SmsLoginBtn, button:has-text('登录')"

# 极验验证码人工等待上限（秒）。超时后视为登录失败，由上层决定降级策略。
MANUAL_CAPTCHA_TIMEOUT = 120.0


async def _login_error_hint(page: Page) -> str:
    """采集登录页上的错误/验证码提示文本，用于失败日志诊断。"""
    try:
        hints = await page.evaluate("""() => {
            const errs = [];
            for (const el of document.querySelectorAll('[class*=error], [class*=tip], [class*=warn]')) {
                const t = (el.innerText || '').trim();
                if (t && t.length < 120) errs.push(t);
            }
            if (errs.length) return [...new Set(errs)].slice(0, 3);
            const t = document.body ? document.body.innerText : '';
            const keys = ['验证', '错误', '密码', '帐号', '不存在', '超时'];
            const found = [];
            for (const k of keys) {
                const i = t.indexOf(k);
                if (i >= 0) found.push(t.slice(Math.max(0, i - 12), i + 24).replace(/\\s+/g, ' ').trim());
            }
            return [...new Set(found)].slice(0, 5);
        }""")
        return " | ".join(hints)
    except Exception:
        return ""


async def login(
    page: Page, site: str, username: str, password: str, manual_wait: float = 0.0
) -> tuple[bool, str]:
    """登录招聘网站。成功返回 (True, "")；失败返回 (False, 原因)，不抛出。

    manual_wait > 0 且检测到极验验证码时，暂停等待人工在有头浏览器窗口中
    完成验证（最多 manual_wait 秒）——用于半自动登录。
    失败原因 "geetest" 表示极验风控拦截，调用方可切换有头模式重试。
    """
    if site != "51job":
        logger.warning("暂不支持的站点登录: %s", site)
        return False, "暂不支持的站点"
    try:
        await page.goto(_LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(1500)
        pwd_input = page.locator(_PASS_INPUT)
        if await pwd_input.count() == 0:
            await page.locator(_PASSWORD_TAB, has_text="密码登录").first.click(timeout=15000)
            await pwd_input.first.wait_for(state="visible", timeout=15000)
        agree = page.locator(_AGREE_LABEL, has_text="我已阅读并同意").first
        if await agree.count() > 0:
            await agree.click(timeout=5000)
        await page.locator(_USER_INPUT).first.fill(username)
        await page.locator(_PASS_INPUT).first.fill(password)
        await page.locator(_SUBMIT).first.click(timeout=15000)
        await page.wait_for_timeout(3000)
        if manual_wait > 0 and await detect_geetest(page):
            logger.warning(
                "检测到极验验证码，请在浏览器窗口中人工完成验证（等待最多 %.0f 秒）",
                manual_wait,
            )
            solved = await wait_geetest_manual(page, timeout=manual_wait)
            if not solved:
                logger.warning("极验人工验证超时，登录失败")
                return False, "极验验证码人工验证超时"
            await page.wait_for_timeout(2000)
        else:
            await solve_aliyun_captcha(page)
            await page.wait_for_timeout(2000)
        if "login.51job.com" in page.url:
            hint = await _login_error_hint(page)
            reason = "geetest" if await detect_geetest(page) else (hint or "未知原因")
            logger.warning(
                "站点登录失败: site=%s username=%s hint=%s url=%s",
                site, username, hint, page.url,
            )
            return False, reason
        logger.info("站点登录成功: site=%s username=%s", site, username)
        return True, ""
    except Exception as exc:
        logger.warning("站点登录异常: site=%s username=%s err=%s", site, username, exc)
        return False, f"登录异常: {exc}"
