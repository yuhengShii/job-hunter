import asyncio
import logging
import random
import time
from pathlib import Path

from playwright.async_api import Page

logger = logging.getLogger("job_hunter")

_SLIDER_SELECTOR = "#aliyunCaptcha-sliding-slider"
_WRAPPER_SELECTOR = "#aliyunCaptcha-sliding-wrapper"
_EMBED_SELECTOR = "#aliyunCaptcha-window-embed"
_ERROR_SELECTOR = "#aliyunCaptcha-sliding-errorCode"

_GEETEST_PANEL = ".geetest_panel"
_GEETEST_HOLDER = ".geetest_holder"
_GEETEST_SUCCESS = ".geetest_panel_success, .geetest_success"

_STEPS = 80
_JITTER = 2.0


def _human_track(distance: float) -> list[float]:
    """拟人轨迹 v2：ease-out 主行程 + 过冲回正 + 抖动与微停顿，总和 = distance。"""
    overshoot = min(6.0, distance * 0.02)
    target = distance + overshoot
    track: list[float] = []
    for i in range(_STEPS):
        t = (i + 1) / _STEPS
        cumulative = target * (1 - (1 - t) ** 3)
        step = cumulative - sum(track)
        if i % 11 == 0:
            step = 0.0
        step += random.uniform(-_JITTER, _JITTER)
        track.append(step)
    correction = sum(track) - distance
    if correction > 0.5:
        for k in range(3):
            step = min(correction / 3.0 + random.uniform(-0.5, 0.5), correction)
            track.append(step)
            correction -= step
    tail = distance - sum(track)
    if abs(tail) > 0.5:
        track[-1] += tail
    return track


async def _is_passed(page: Page) -> bool:
    box = page.locator(_EMBED_SELECTOR)
    if await box.count() == 0:
        return True
    cls = await box.get_attribute("class") or ""
    return "aliyunCaptcha-show" not in cls


async def wait_aliyun_manual(page: Page, timeout: float = 120.0, poll_interval: float = 1.0) -> bool:
    """有头模式下等待人工完成阿里云滑块验证（滑块面板消失/通过）。

    轮询 _is_passed 判断；超时或页面关闭返回 False。页面导航导致的瞬态异常
    记录日志后继续等待。
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if page.is_closed():
            logger.warning("滑块人工等待中断：页面已关闭")
            return False
        try:
            if await _is_passed(page):
                return True
        except Exception as exc:
            logger.warning("滑块人工等待轮询异常（继续等待）: %s", exc)
        await asyncio.sleep(poll_interval)
    logger.warning("滑块人工等待超时（%.0f 秒）", timeout)
    return False


async def detect_geetest(page: Page) -> bool:
    """检测页面是否出现极验 geetest 验证码（面板或容器元素存在）。

    51job 登录页实测（2026-08）使用极验 fullpage/wind 主题，
    风控拒绝时会以「网络超时」伪错误展示，因此按容器存在性判断。
    """
    for sel in (_GEETEST_PANEL, _GEETEST_HOLDER):
        if await page.locator(sel).count() > 0:
            return True
    return False


async def wait_geetest_manual(page: Page, timeout: float = 120.0, poll_interval: float = 1.0) -> bool:
    """有头模式下等待人工完成极验验证码。

    轮询「成功面板可见」或「URL 已离开 login.51job.com」判断完成；
    超时返回 False。页面导航导致的瞬态异常（execution context 销毁等）
    记录日志后继续等待，仅页面真正关闭才终止。
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if page.is_closed():
            logger.warning("极验人工等待中断：页面已关闭")
            await _dump_screenshot(page, "closed")
            return False
        try:
            done = await page.evaluate(
                """() => {
                    const el = document.querySelector('.geetest_panel_success, .geetest_success');
                    if (el && (el.offsetWidth || el.offsetHeight)) return true;
                    return !location.href.includes('login.51job.com');
                }"""
            )
        except Exception as exc:
            # 页面导航/刷新期间的瞬态异常：不能当作人工超时
            logger.warning("极验人工等待轮询异常（继续等待）: %s", exc)
            await asyncio.sleep(poll_interval)
            continue
        if done:
            return True
        await asyncio.sleep(poll_interval)
    logger.warning("极验人工等待超时（%.0f 秒）", timeout)
    await _dump_screenshot(page, "timeout")
    return False


async def _dump_screenshot(page: Page, tag: str) -> None:
    """保存当前页面截图到 logs/，用于诊断人工验证窗口的实际状态。"""
    try:
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = Path(__file__).resolve().parents[3] / "logs" / f"geetest_manual_{tag}_{ts}.png"
        await page.screenshot(path=str(path))
        logger.warning("已保存诊断截图: %s", path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("诊断截图失败: %s", exc)


async def solve_aliyun_captcha(page: Page, max_attempts: int = 3) -> bool:
    for attempt in range(1, max_attempts + 1):
        try:
            slider = page.locator(_SLIDER_SELECTOR)
            wrapper = page.locator(_WRAPPER_SELECTOR)
            if await slider.count() == 0 or await wrapper.count() == 0:
                return await _is_passed(page)
            if await _is_passed(page):
                return True
            sb = await slider.bounding_box()
            wb = await wrapper.bounding_box()
            if not sb or not wb:
                return False
            start_x = sb["x"] + sb["width"] / 2
            y = sb["y"] + sb["height"] / 2
            target_x = wb["x"] + wb["width"] - sb["width"] / 2
            distance = target_x - start_x
            if distance <= 0:
                return await _is_passed(page)
            await page.mouse.move(start_x, y)
            await page.wait_for_timeout(random.uniform(200, 500))   # hover 停顿
            await page.mouse.down()
            await page.mouse.move(start_x + random.uniform(1.0, 2.5), y)  # 按下后微动
            await page.wait_for_timeout(random.uniform(60, 150))
            pos = start_x
            for dx in _human_track(distance):
                pos += dx
                await page.mouse.move(pos, y)
                await asyncio.sleep(random.uniform(0.015, 0.04))
            await page.wait_for_timeout(random.uniform(50, 120))
            await page.mouse.up()
            await page.wait_for_timeout(random.uniform(1200, 2500))
            if await _is_passed(page):
                logger.info("滑块验证通过 (attempt %s)", attempt)
                return True
            err = page.locator(_ERROR_SELECTOR)
            if await err.count() > 0:
                try:
                    txt = (await err.first.inner_text()).strip()
                except Exception:
                    txt = ""
                logger.warning("滑块验证失败 (attempt %s): %s", attempt, txt)
            await page.wait_for_timeout(random.uniform(1000, 2000))
        except Exception as exc:
            logger.warning("滑块验证异常 (attempt %s): %s", attempt, exc)
            return False
    return False
