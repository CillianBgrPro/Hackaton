"""Lecture simplifiée du format opening_hours d'OpenStreetMap.

Couvre les cas courants : « Mo-Sa 07:00-20:00; Su 08:00-13:00 », plages multiples, passage de minuit,
« 24/7 », « off ». Les règles plus rares (jours fériés, mois, lever du soleil…) sont ignorées :
un horaire illisible est traité comme « non renseigné ».
"""
import re

DAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
_DAY = r"(?:Mo|Tu|We|Th|Fr|Sa|Su)"


def _days(selector):
    days = set()
    for part in selector.split(","):
        m = re.fullmatch(rf"({_DAY})(?:\[[^\]]*\])?(?:-({_DAY}))?", part.strip())
        if not m:
            return None
        a = DAYS.index(m.group(1))
        b = DAYS.index(m.group(2)) if m.group(2) else a
        i = a
        while True:
            days.add(i)
            if i == b:
                break
            i = (i + 1) % 7
    return days


def _ranges(text):
    out = []
    for part in text.split(","):
        m = re.fullmatch(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\+?", part.strip())
        if not m:
            return None
        start = int(m.group(1)) * 60 + int(m.group(2))
        end = int(m.group(3)) * 60 + int(m.group(4))
        out.append((start, end + 1440 if end <= start else end))
    return out


def parse(value):
    """{jour (0 = lundi): [(début, fin)]} en minutes, fin > 1440 après minuit ; None si illisible."""
    if not value:
        return None
    s = value.strip()
    if s in ("24/7", "Mo-Su 00:00-24:00", "00:00-24:00"):
        return {d: [(0, 1440)] for d in range(7)}
    week, understood = {}, False
    for rule in re.split(r";|\|\|", s):
        r = rule.strip()
        if not r or re.match(r"^(PH|SH|easter|week|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|\d{4})", r):
            continue
        r = re.sub(r"\bPH\b,?|,?\bPH\b|\bSH\b,?", "", r).strip()
        m = re.match(rf"^((?:{_DAY}(?:\[[^\]]*\])?(?:-{_DAY})?,?\s*)+)?(.*)$", r)
        selector, rest = (m.group(1) or "").strip().rstrip(","), m.group(2).strip()
        days = _days(selector) if selector else set(range(7))
        if days is None:
            continue
        if rest.lower() in ("off", "closed"):
            week.update({d: [] for d in days})
            understood = True
            continue
        ranges = [(0, 1440)] if rest in ("24/7", "00:00-24:00") else _ranges(rest)
        if ranges:
            week.update({d: ranges for d in days})
            understood = True
    return week if understood else None


def closing(week, day):
    """Heure de fermeture (minutes) d'un jour donné, ou None s'il est fermé."""
    return max((end for _, end in week.get(day, [])), default=None) if week else None


def is_open(week, day, minute):
    if not week:
        return None
    if any(a <= minute < b for a, b in week.get(day, [])):
        return True
    return any(b > 1440 and minute < b - 1440 for _, b in week.get((day - 1) % 7, []))
