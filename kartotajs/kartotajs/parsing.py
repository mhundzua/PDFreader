"""OCR teksta pārvēršana līguma Nr., sērijas Nr. un datumā.

OCR rokrakstā bieži sajauc ciparus ar līdzīgiem burtiem (piemēram, rokrakstā
rakstīts "2" tiek nolasīts kā "d"). Laukos, kur var būt tikai cipari, šos
burtus pārvēršam atpakaļ ciparos.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
from typing import Optional

# Burti, kurus OCR rokrakstā mēdz nolasīt cipara vietā.
DIGIT_LOOKALIKES = {
    "o": "0", "O": "0", "D": "0", "Q": "0", "°": "0",
    "i": "1", "I": "1", "l": "1", "L": "1", "|": "1", "!": "1", "j": "1",
    "z": "2", "Z": "2", "d": "2", "ℒ": "2", "ẑ": "2",
    "h": "4", "H": "4", "A": "4",
    "s": "5", "S": "5",
    "b": "6", "G": "6",
    "y": "7", "Y": "7", "T": "7", "t": "7",
    "B": "8",
    "g": "9", "q": "9",
}

CONTRACT_SEARCH_RE = re.compile(r"R[O0Q]V[\W_]{0,3}([0-9OoQDIl|]{6})(?![0-9])")


def ascii_upper(text: str) -> str:
    """Noņem diakritiskās zīmes un atstarpes: 'LĪGUMA Nr.:' -> 'LIGUMANR'."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def to_digits(text: str) -> str:
    """Pārvērš līdzīgos burtus ciparos; citus simbolus atstāj neskartus."""
    return "".join(DIGIT_LOOKALIKES.get(ch, ch) for ch in text)


def find_contract(text: str) -> Optional[str]:
    m = CONTRACT_SEARCH_RE.search(text.replace(" ", ""))
    if not m:
        return None
    return "ROV_" + to_digits(m.group(1))


def find_serial(text: str) -> Optional[str]:
    """Garākā ciparu virkne (pēc burtu pārvēršanas). Priekšroka 6 cipariem."""
    digits = to_digits(text)
    runs = re.findall(r"\d+", digits)
    # Ja OCR starp cipariem ielicis atstarpi, mēģinām arī salipināt.
    joined = re.findall(r"\d[\d ]*\d", digits)
    candidates = runs + [j.replace(" ", "") for j in joined]
    candidates = [c for c in candidates if 4 <= len(c) <= 10]
    if not candidates:
        return None
    six = [c for c in candidates if len(c) == 6]
    if six:
        return six[0]
    return max(candidates, key=len)


_SEP = r"\s*[.,\-/ ·:]\s*"
_DATE_RE = re.compile(rf"(?<!\d)(\d{{1,2}}){_SEP}(\d{{1,2}}){_SEP}(\d{{4}}|\d{{2}})(?!\d)")
_DAY_MONTH_RE = re.compile(rf"(?<!\d)(\d{{1,2}}){_SEP}(\d{{2}})")


def find_date(text: str, today: Optional[dt.date] = None) -> Optional[dt.date]:
    """Atrod datumu formātā dd.mm.gg vai dd.mm.gggg (punkts beigās neobligāts)."""
    today = today or dt.date.today()
    digits = to_digits(text)
    for m in _DATE_RE.finditer(digits):
        day, month, year = int(m.group(1)), int(m.group(2)), m.group(3)
        y = int(year) + (2000 if len(year) == 2 else 0)
        if not (2000 <= y <= today.year + 1):
            continue
        try:
            return dt.date(y, month, day)
        except ValueError:
            continue
    # Bez atdalītājiem: "290826" vai "29082026".
    compact = re.sub(r"[^\d]", "", digits)
    for fmt in ("%d%m%Y", "%d%m%y"):
        size = 8 if fmt.endswith("Y") else 6
        if len(compact) == size:
            try:
                d = dt.datetime.strptime(compact, fmt).date()
            except ValueError:
                continue
            if 2000 <= d.year <= today.year + 1:
                return d
    return None


def find_day_month(text: str, today: Optional[dt.date] = None) -> Optional[dt.date]:
    """Rezerves variants, ja gads nav salasāms (rokrakstā '2026' bieži kļūst par 'd0d6').

    Ņem dienu un mēnesi, gadu pieņem jaunāko, kas nav nākotnē.
    """
    today = today or dt.date.today()
    for m in _DAY_MONTH_RE.finditer(to_digits(text)):
        day, month = int(m.group(1)), int(m.group(2))
        for year in (today.year, today.year - 1):
            try:
                d = dt.date(year, month, day)
            except ValueError:
                break
            if d <= today:
                return d
    return None
