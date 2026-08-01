import logging
import re

logger = logging.getLogger("job_hunter")

_PATTERNS: list[tuple[re.Pattern, int, bool]] = [
    (re.compile(r"^年薪([\d.]+)-([\d.]+)万"), 10000, True),
    (re.compile(r"^([\d.]+)-([\d.]+)万(?:/月)?"), 10000, False),
    (re.compile(r"^([\d.]+)-([\d.]+)千(?:/月)?"), 1000, False),
    (re.compile(r"^([\d.]+)-([\d.]+)\s*[Kk](?:/月)?"), 1000, False),
]
_MIXED_KWAN_RE = re.compile(r"^([\d.]+)千-([\d.]+)万(?:/月)?")
_SUFFIX_RE = re.compile(r"[\s·*]*\d+薪.*$")


def parse_salary(raw: str | None) -> tuple[int | None, int | None]:
    if not raw:
        return None, None
    text = raw.strip()
    if text == "面议":
        return None, None
    text = _SUFFIX_RE.sub("", text).strip()
    m = _MIXED_KWAN_RE.match(text)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        if lo >= 1 and hi >= 1:
            return int(lo * 1000), int(hi * 10000)
    for pat, unit, annual in _PATTERNS:
        m = pat.match(text)
        if m:
            lo, hi = float(m.group(1)), float(m.group(2))
            if lo < 1 or hi < lo:
                continue
            factor = unit / 12 if annual else unit
            return int(lo * factor), int(hi * factor)
    logger.warning("无法解析薪资: %r", raw)
    return None, None
