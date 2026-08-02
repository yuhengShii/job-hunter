import asyncio

import pytest

from backend.app.scrapers.captcha import _human_track, solve_aliyun_captcha

BBOX_SLIDER = {"x": 20.0, "y": 100.0, "width": 40.0, "height": 30.0}
BBOX_WRAPPER = {"x": 10.0, "y": 95.0, "width": 300.0, "height": 40.0}


class FakeMouse:
    def __init__(self):
        self.moves = []
        self.downs = 0
        self.ups = 0

    async def move(self, x, y):
        self.moves.append((x, y))

    async def down(self):
        self.downs += 1

    async def up(self):
        self.ups += 1


class FakeLocator:
    def __init__(self, count=0, bbox=None, attr=None, text=""):
        self._count = count
        self._bbox = bbox
        self._attr = attr
        self._text = text
        self.first = self

    async def count(self):
        return self._count

    async def bounding_box(self):
        return self._bbox

    async def get_attribute(self, name):
        return self._attr

    async def inner_text(self):
        return self._text


class FakePage:
    def __init__(self, specs):
        self._specs = specs
        self.mouse = FakeMouse()
        self.waits = []

    def locator(self, sel):
        return self._specs[sel]

    async def wait_for_timeout(self, ms):
        self.waits.append(ms)


def _specs(slider_count=1, wrapper_count=1, embed_attr="aliyunCaptcha-show", error_text=""):
    return {
        "#aliyunCaptcha-sliding-slider": FakeLocator(slider_count, BBOX_SLIDER),
        "#aliyunCaptcha-sliding-wrapper": FakeLocator(wrapper_count, BBOX_WRAPPER),
        "#aliyunCaptcha-window-embed": FakeLocator(1, None, embed_attr),
        "#aliyunCaptcha-sliding-errorCode": FakeLocator(1, None, None, error_text),
    }


async def _noop_sleep(delay):
    pass


def test_human_track_total_distance():
    track = _human_track(300.0)
    assert len(track) == 50
    assert abs(sum(track) - 300.0) < 2.0


def test_solve_success_drags_full_distance(monkeypatch):
    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)
    page = FakePage(_specs())
    async def run():
        return await solve_aliyun_captcha(page)
    assert asyncio.run(run()) is True
    assert page.mouse.downs == 1
    assert page.mouse.ups == 1
    first = page.mouse.moves[0][0]
    last = page.mouse.moves[-1][0]
    start_x = BBOX_SLIDER["x"] + BBOX_SLIDER["width"] / 2
    distance = (BBOX_WRAPPER["x"] + BBOX_WRAPPER["width"] - BBOX_SLIDER["width"]) - start_x
    assert first == start_x
    assert abs(last - (start_x + distance)) < 2.0
    assert len(page.mouse.moves) >= 40


def test_solve_failure_retries_max_attempts(monkeypatch):
    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)
    page = FakePage(_specs(error_text="拖动失败，请重试"))
    async def run():
        return await solve_aliyun_captcha(page, max_attempts=3)
    assert asyncio.run(run()) is False
    assert page.mouse.downs == 3
    assert page.mouse.ups == 3


def test_solve_passed_when_embed_hidden(monkeypatch):
    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)
    page = FakePage(_specs(embed_attr="aliyunCaptcha-hidden"))
    async def run():
        return await solve_aliyun_captcha(page)
    assert asyncio.run(run()) is True
    assert page.mouse.downs == 0  # 已通过，不拖动


def test_solve_missing_slider_returns_false(monkeypatch):
    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)
    page = FakePage(_specs(slider_count=0, wrapper_count=0, embed_attr="aliyunCaptcha-show"))
    async def run():
        return await solve_aliyun_captcha(page)
    assert asyncio.run(run()) is False
    assert page.mouse.downs == 0
