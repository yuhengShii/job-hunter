import logging

from playwright.async_api import Page

from backend.app.scrapers.captcha import solve_aliyun_captcha

logger = logging.getLogger("job_hunter")

_LOGIN_URL = "https://login.51job.com/login.php?lang=c"
_USER_INPUT = "input[placeholder*='手机号'], input[name='phone'], input[type='tel']"
_PASS_INPUT = "input[placeholder*='密码'], input[type='password']"
_SUBMIT = "button[type='submit'], .login-btn, button:has-text('登 录'), button:has-text('登录')"


async def login(page: Page, site: str, username: str, password: str) -> bool:
    """登录招聘网站。成功返回 True；失败/验证码未过/异常返回 False（不抛出）。"""
    if site != "51job":
        logger.warning("暂不支持的站点登录: %s", site)
        return False
    try:
        await page.goto(_LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(1500)
        await page.locator(_USER_INPUT).first.fill(username)
        await page.locator(_PASS_INPUT).first.fill(password)
        await page.locator(_SUBMIT).first.click(timeout=15000)
        await page.wait_for_timeout(3000)
        await solve_aliyun_captcha(page)
        await page.wait_for_timeout(2000)
        if "login.51job.com" in page.url:
            return False
        logger.info("站点登录成功: site=%s username=%s", site, username)
        return True
    except Exception as exc:
        logger.warning("站点登录异常: site=%s username=%s err=%s", site, username, exc)
        return False
