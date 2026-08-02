import asyncio
import logging
import random

from playwright.async_api import Page

logger = logging.getLogger("job_hunter")

_SLIDER_SELECTOR = "#aliyunCaptcha-sliding-slider"
_WRAPPER_SELECTOR = "#aliyunCaptcha-sliding-wrapper"
_EMBED_SELECTOR = "#aliyunCaptcha-window-embed"
_ERROR_SELECTOR = "#aliyunCaptcha-sliding-errorCode"

_STEPS = 50
_JITTER = 2.0


def _human_track(distance: float) -> list[float]:
    """ease-out 拟人轨迹：分段位移，带随机抖动与微停顿，总和 = distance。"""
    track: list[float] = []
    remaining = distance
    for i in range(_STEPS):
        t = (i + 1) / _STEPS
        cumulative = distance * (1 - (1 - t) ** 3)
        step = cumulative - sum(track)
        if i % 13 == 0:
            step = 0.0
        step += random.uniform(-_JITTER, _JITTER)
        step = max(0.0, min(remaining, step))
        track.append(step)
        remaining -= step
    if remaining > 0.5:
        track[-1] += remaining
    return track


async def _is_passed(page: Page) -> bool:
    box = page.locator(_EMBED_SELECTOR)
    if await box.count() == 0:
        return True
    cls = await box.get_attribute("class") or ""
    return "aliyunCaptcha-show" not in cls


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
            distance = (wb["x"] + wb["width"] - sb["width"]) - start_x
            if distance <= 0:
                return await _is_passed(page)
            await page.mouse.move(start_x, y)
            await page.mouse.down()
            pos = start_x
            for dx in _human_track(distance):
                pos += dx
                await page.mouse.move(pos, y)
                await asyncio.sleep(random.uniform(0.01, 0.025))
            await page.mouse.up()
            await page.wait_for_timeout(random.uniform(1000, 2000))
            if await _is_passed(page):
                logger.info("滑块验证通过 (attempt %s)", attempt)
                return True
            err = page.locator(_ERROR_SELECTOR)
            if await err.count() > 0 and (await err.first.inner_text()).strip():
                logger.warning("滑块验证失败 (attempt %s)", attempt)
                await page.wait_for_timeout(random.uniform(1000, 2000))
                continue
            # 无错误提示且未判定失败：视为通过（阿里云通过后 errorCode 无文本）
            logger.info("滑块验证通过 (attempt %s)", attempt)
            return True
        except Exception as exc:
            logger.warning("滑块验证异常 (attempt %s): %s", attempt, exc)
            return False
    return False
