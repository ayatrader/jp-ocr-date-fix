"""Find Japanese dates in OCR text, repair common character confusions, and keep a fix only
when the repaired date exists on the calendar.

Rules (standard library only, no network):
- A span is a date candidate only when it has the full shape  ERA + YEAR + 年 + MONTH + 月 [+ DAY + 日]
  or  YYYY + 年 + MONTH + 月 [+ DAY + 日].  Single characters are never changed outside such a span.
- Each character is mapped through a fixed confusion table (e.g. 今→令, 曰→日, O→0, l→1).
- The repaired date must exist (month 1-12, real day, inside the era's range). Otherwise nothing is
  changed and the span is reported in `flags` so a person or an AI can look at it.
"""
from __future__ import annotations

import datetime as _dt
import re
import unicodedata

D = _dt.date

# era: (first day, last day)
ERAS = {
    "明治": (D(1868, 10, 23), D(1912, 7, 29)),
    "大正": (D(1912, 7, 30), D(1926, 12, 24)),
    "昭和": (D(1926, 12, 25), D(1989, 1, 7)),
    "平成": (D(1989, 1, 8), D(2019, 4, 30)),
    "令和": (D(2019, 5, 1), None),
}

# OCR look-alikes seen in Japanese documents. Key = correct character, value = characters OCR returns.
CONFUSIONS = {
    "令": "今合命冷伶", "和": "私利知秈", "平": "乎半干千", "成": "戒威戍戌",
    "昭": "照招", "明": "朋眀", "治": "冶洽", "大": "太犬", "正": "止玉",
    "元": "兀无",
    "年": "午牛", "月": "用円丹", "日": "曰目口ロ",
}
DIGITS = {"0": "OoＯｏDＤ〇○", "1": "lIｌＩ|｜丨!", "2": "Z", "5": "S", "8": "B"}
# 〇 is a valid kanji zero; we still map it to 0 because it is a digit inside a date.

_TO_RIGHT = {}
for right, wrongs in {**CONFUSIONS, **DIGITS}.items():
    for w in wrongs:
        _TO_RIGHT[w] = right


def _cls(right: str, extra: str = "") -> str:
    return "[" + re.escape(right + CONFUSIONS.get(right, "") + extra) + "]"


_DIG = "[0-9０-９" + re.escape("".join(DIGITS.values())) + "]"
_NUM = f"{_DIG}{{1,2}}"
_ERA1 = "".join(e[0] + CONFUSIONS.get(e[0], "") for e in ERAS)
_ERA2 = "".join(e[1] + CONFUSIONS.get(e[1], "") for e in ERAS)
_SP = r"[ 　]?"
_ERA_RE = re.compile(
    f"(?P<era>[{re.escape(_ERA1)}][{re.escape(_ERA2)}]){_SP}(?P<y>{_NUM}|{_cls('元')}){_SP}{_cls('年')}{_SP}"
    f"(?P<m>{_NUM}){_SP}{_cls('月')}(?:{_SP}(?P<d>{_NUM}){_SP}{_cls('日')})?"
)
# Western year: first digit must be a real 1 or 2 (or a look-alike of 1) to avoid matching codes.
_WEST_RE = re.compile(
    f"(?<![0-9０-９])(?P<y>[12１２lIｌＩ|｜]{_DIG}{{3}}){_SP}{_cls('年')}{_SP}(?P<m>{_NUM}){_SP}{_cls('月')}"
    f"(?:{_SP}(?P<d>{_NUM}){_SP}{_cls('日')})?"
)


def _fix_chars(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    return "".join(_TO_RIGHT.get(c, c) for c in s)


def _num(s: str) -> int:
    t = unicodedata.normalize("NFKC", s)
    t = "".join(_TO_RIGHT.get(c, c) for c in t)
    return int(t)


def _era_of(two: str):
    fixed = "".join(_TO_RIGHT.get(c, c) for c in two)
    return fixed if fixed in ERAS else None


def _valid_era_date(era: str, year: int, month: int, day):
    start, end = ERAS[era]
    if year < 1 or not 1 <= month <= 12:
        return None, "month out of range" if year >= 1 else "year out of range"
    try:
        d = D(start.year + year - 1, month, day or 1)
    except ValueError:
        return None, "day does not exist"
    last = end or D(9999, 12, 31)
    if day is None:
        # year-month only: the month must overlap the era
        month_end = (D(d.year + (month == 12), month % 12 + 1, 1) - _dt.timedelta(days=1))
        ok = month_end >= start and d <= last
    else:
        ok = start <= d <= last
    return (d if ok else None), (None if ok else f"date is outside {era}")


def _render(era, year, month, day):
    y = "元" if era and year == 1 else str(year)
    head = f"{era}{y}年" if era else f"{year}年"
    return head + f"{month}月" + (f"{day}日" if day is not None else "")


def _check_match(m, kind):
    raw = m.group(0)
    try:
        if kind == "era":
            era = _era_of(m.group("era"))
            if not era:
                return None
            yraw = m.group("y")
            year = 1 if _TO_RIGHT.get(yraw, yraw) == "元" else _num(yraw)
        else:
            era, year = None, _num(m.group("y"))
        month = _num(m.group("m"))
        day = _num(m.group("d")) if m.group("d") else None
    except ValueError:
        return {"kind": "flag", "before": raw, "reason": "digits could not be read"}
    if era:
        d, why = _valid_era_date(era, year, month, day)
    else:
        why = None
        d = None
        if not 1868 <= year <= 2100:
            why = "year out of range"
        else:
            try:
                d = D(year, month, day or 1)
            except ValueError:
                why = "day does not exist" if 1 <= month <= 12 else "month out of range"
    if d is None:
        return {"kind": "flag", "before": raw, "reason": why}
    iso = d.isoformat() if day is not None else d.isoformat()[:7]
    # keep the original spacing/format if nothing is wrong
    if _fix_chars(raw) == raw and raw == unicodedata.normalize("NFKC", raw):
        return {"kind": "ok", "before": raw, "iso": iso}
    return {"kind": "fix", "before": raw, "after": _render(era, year, month, day), "iso": iso}


def check_date(s: str) -> dict:
    """Check one date string. Returns status ok / fixed / invalid / not_a_date."""
    s = s.strip()
    for kind, rx in (("era", _ERA_RE), ("west", _WEST_RE)):
        m = rx.fullmatch(s)
        if m:
            r = _check_match(m, kind)
            if r is None:
                continue
            if r["kind"] == "ok":
                return {"input": s, "status": "ok", "date": s, "iso": r["iso"]}
            if r["kind"] == "fix":
                return {"input": s, "status": "fixed", "date": r["after"], "iso": r["iso"]}
            return {"input": s, "status": "invalid", "reason": r["reason"]}
    return {"input": s, "status": "not_a_date"}


def fix_text(text: str) -> dict:
    """Repair dates inside OCR text. Returns the new text, each change, and spans left for review."""
    hits = []
    for kind, rx in (("era", _ERA_RE), ("west", _WEST_RE)):
        for m in rx.finditer(text):
            r = _check_match(m, kind)
            if r:
                hits.append((m.start(), m.end(), r))
    hits.sort(key=lambda h: (h[0], -(h[1] - h[0])))
    out, changes, flags, pos = [], [], [], 0
    for start, end, r in hits:
        if start < pos:
            continue  # overlapping (e.g. western match inside era match)
        out.append(text[pos:start])
        if r["kind"] == "fix":
            out.append(r["after"])
            changes.append({"start": start, "end": end, "before": r["before"], "after": r["after"], "iso": r["iso"]})
        else:
            out.append(text[start:end])
            if r["kind"] == "flag":
                flags.append({"start": start, "end": end, "text": r["before"], "reason": r["reason"]})
        pos = end
    out.append(text[pos:])
    return {"text": "".join(out), "changes": changes, "flags": flags}
