"""Faila nosaukuma un mapes veidošana, lauku validācija."""

from __future__ import annotations

import datetime as dt
import re
from typing import Optional

MONTHS_LV = [
    "", "Janvāris", "Februāris", "Marts", "Aprīlis", "Maijs", "Jūnijs",
    "Jūlijs", "Augusts", "Septembris", "Oktobris", "Novembris", "Decembris",
]

CONTRACT_RE = re.compile(r"^ROV_\d{6}$")
SERIAL_RE = re.compile(r"^[0-9A-Za-z-]+$")


def folder_name(date: dt.date) -> str:
    return f"{date.year}-{MONTHS_LV[date.month]}"


def file_name(contract: str, serial: str) -> str:
    return f"{contract}-{serial}.pdf"


def parse_iso(value: str) -> Optional[dt.date]:
    try:
        return dt.date.fromisoformat((value or "").strip())
    except ValueError:
        return None


def validate(contract: str, serial: str, date_iso: str) -> tuple[dict, list[str]]:
    """Atgriež (kļūdas pa laukiem, brīdinājumi). Kļūdas bloķē akceptēšanu."""
    errors: dict[str, str] = {}
    warnings: list[str] = []
    contract = (contract or "").strip()
    serial = (serial or "").strip()
    if not CONTRACT_RE.match(contract):
        errors["contract"] = "Līguma Nr. jābūt formātā ROV_ + 6 cipari"
    if not serial:
        errors["serial"] = "Sērijas Nr. nav norādīts"
    elif not SERIAL_RE.match(serial):
        errors["serial"] = "Sērijas Nr. drīkst saturēt tikai burtus, ciparus un '-'"
    elif not (serial.isdigit() and len(serial) == 6):
        warnings.append("Sērijas Nr. nav 6 cipari, lūdzu pārbaudiet")
    date = parse_iso(date_iso)
    if date is None:
        errors["date"] = "Datums nav derīgs"
    elif date > dt.date.today():
        warnings.append("Datums ir nākotnē, lūdzu pārbaudiet")
    return errors, warnings
