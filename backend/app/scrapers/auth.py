import logging

from playwright.async_api import Page

from backend.app.scrapers.captcha import solve_aliyun_captcha

logger = logging.getLogger("job_hunter")

_LOGIN_URL = "https://login.51job.com/login.php?lang=c"
# 实测（2026-08）：登录页默认「手机号 + 短信验证码」模式，需先点「密码登录」tab 才出现密码框；
# 提交前需点击协议同意 label（#isread 隐藏 checkbox）；提交按钮为 div#SmsLoginBtn
_USER_INPUT = "#loginname"
_PASS_INPUT = "#password"
_PASSWORD_TAB = "span.loginway"
_AGREE_LABEL = "label"
_SUBMIT = "#SmsLoginBtn, button:has-text('登录')"


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


async def login(page: Page, site: str, username: str, password: str) -> bool:
    """登录招聘网站。成功返回 True；失败/验证码未过/异常返回 False（不抛出）。"""
    if site != "51job":
        logger.warning("暂不支持的站点登录: %s", site)
        return False
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
        await solve_aliyun_captcha(page)
        await page.wait_for_timeout(2000)
        if "login.51job.com" in page.url:
            hint = await _login_error_hint(page)
            logger.warning(
                "站点登录失败: site=%s username=%s hint=%s url=%s",
                site, username, hint, page.url,
            )
            return False
        logger.info("站点登录成功: site=%s username=%s", site, username)
        return True
    except Exception as exc:
        logger.warning("站点登录异常: site=%s username=%s err=%s", site, username, exc)
        return False
