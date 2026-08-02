import asyncio
import logging
import random

from playwright.async_api import Page

logger = logging.getLogger("job_hunter")

_SLIDER_SELECTOR = "#aliyunCaptcha-sliding-slider"
_WRAPPER_SELECTOR = "#aliyunCaptcha-sliding-wrapper"
_EMBED_SELECTOR = "#aliyunCaptcha-window-embed"
_ERROR_SELECTOR = "#aliyunCaptcha-sliding-errorCode"

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
