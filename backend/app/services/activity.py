import math
import re

_UNKNOWN = -1

_QUALITATIVE = {
    "刚刚活跃": 10,
    "今日活跃": 9,
    "回复率高": 8,
    "简历处理快": 7,
    "喜欢聊天": 6,
}

_RE_COUNT = re.compile(r"^今日回复(\d+)(\+)?次$")
_RE_MINUTES = re.compile(r"^(\d+)分钟前(回复|处理简历)$")
_RE_DAYS = re.compile(r"^(\d+)天内处理简历$")
_RE_ACTIVE_DAYS = re.compile(r"^(\d+)天$")


def _score_label(label: str) -> int | None:
    label = label.strip()
    if label in _QUALITATIVE:
        return _QUALITATIVE[label]
    m = _RE_COUNT.match(label)
    if m:
        return min(int(m.group(1)), 10)
    m = _RE_MINUTES.match(label)
    if m:
        minutes = int(m.group(1))
        if minutes <= 1:
            return 10
        return max(0, 10 - math.ceil(minutes / 2))
    m = _RE_DAYS.match(label) or _RE_ACTIVE_DAYS.match(label)
    if m:
        return max(1, 11 - int(m.group(1)))
    return None


def score_activity(text: str | None) -> int:
    if not text:
        return _UNKNOWN
    scores = []
    for part in text.split("、"):
        s = _score_label(part)
        if s is not None:
            scores.append(s)
    return max(scores) if scores else _UNKNOWN
