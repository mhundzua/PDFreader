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


def split_serials(serial: str) -> list[str]:
    """'127668; 219044' -> ['127668', '219044'] (divi alkometri vienā kvītī)."""
    return [s.strip() for s in (serial or "").split(";") if s.strip()]


def file_name(contract: str, serial: str) -> str:
    """ROV_043396-127668.pdf vai, ja ir divi alkometri, ROV_043396-127668;219044.pdf"""
    return f"{contract}-{';'.join(split_serials(serial))}.pdf"


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
    serials = split_serials(serial)
    if not CONTRACT_RE.match(contract):
        errors["contract"] = "Līguma Nr. jābūt formātā ROV_ + 6 cipari"
    if not serials:
        errors["serial"] = "Sērijas Nr. nav norādīts"
    elif not all(SERIAL_RE.match(s) for s in serials):
        errors["serial"] = "Sērijas Nr. drīkst saturēt tikai burtus, ciparus un '-'"
    elif len(set(serials)) != len(serials):
        errors["serial"] = "Abi sērijas numuri ir vienādi"
    else:
        for s in serials:
            if s.isdigit() and len(s) != 6:
                warnings.append(f"Sērijas Nr. {s} nav 6 cipari, lūdzu pārbaudiet")
    date = parse_iso(date_iso)
    if date is None:
        errors["date"] = "Datums nav derīgs"
    elif date > dt.date.today():
        warnings.append("Datums ir nākotnē, lūdzu pārbaudiet")
    return errors, warnings
