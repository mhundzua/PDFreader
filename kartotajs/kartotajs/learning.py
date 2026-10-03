"""Mācīšanās no apstiprinātajām kvītīm.

OCR jūsu darbinieku rokrakstā kļūdās konsekventi: piemēram, kāda rokraksta "4"
vienmēr tiek nolasīts kā "y", bet "1" kā "t". Pēc katras akceptēšanas zinām gan
OCR nolasīto tekstu, gan pareizo vērtību. No tiem saskaitām, kurš OCR simbols
kuram ciparam atbilst, un turpmāk šo tabulu izmantojam teksta pārvēršanai ciparos.

Katram OCR dzinējam tabula ir sava, jo dzinēji kļūdās atšķirīgi.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Optional

from . import parsing

log = logging.getLogger(__name__)

MIN_COUNT = 3      # cik reizes simbolam jāparādās, lai no tā mācītos
MIN_SHARE = 0.6    # cik bieži tam jānozīmē viens un tas pats cipars
MIN_MATCH = 0.6    # cik daļai simbolu jau jāsakrīt, lai nolasījumu uzskatītu par šī lauka


def truth_digits(field: str, value: str) -> list[str]:
    """Apstiprinātās vērtības cipari tādā secībā, kā tie rakstīti uz kvīts."""
    if field == "date":
        m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", value)
        if not m:
            return []
        y, mo, d = m.groups()
        return [d + mo + y, d + mo + y[2:]]  # 29.08.2026 vai 29.08.26
    return [s for s in value.split(";") if s.isdigit()]


def _clean(text: str) -> str:
    """OCR teksts bez atstarpēm un atdalītājiem (cipari un burti paliek)."""
    return re.sub(r"[\s.,\-/·:;_]", "", parsing.strip_sn_prefix(text))


def aligned_pairs(raw: str, truths: Iterable[str]) -> list[tuple[str, str]]:
    """Atrod nolasījumā vietu, kas atbilst pareizajai vērtībai, un atgriež
    (OCR simbols, pareizais cipars) pārus. Ja atbilstība vāja, atgriež []."""
    raw = _clean(raw)
    best: list[tuple[str, str]] = []
    best_score = 0.0
    for truth in truths:
        n = len(truth)
        for start in range(0, len(raw) - n + 1):
            chunk = raw[start:start + n]
            score = sum(parsing.to_digits(c) == t for c, t in zip(chunk, truth)) / n
            if score > best_score:
                best_score, best = score, list(zip(chunk, truth))
    return best if best_score >= MIN_MATCH else []


class Corrections:
    """Iemācītās OCR simbolu → ciparu tabulas pa dzinējiem."""

    def __init__(self) -> None:
        self.counts: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
        self.samples = 0
        self.by_field: Counter = Counter()
        # Sērijas Nr. pirmais cipars: kādi ir patiesībā un ko OCR tā vietā nolasa.
        self.first_true: Counter = Counter()
        self.first_seen: dict[str, Counter] = defaultdict(Counter)

    def add(self, field: str, value: str, readings: Iterable[tuple[str, str]]) -> None:
        """readings: (avots "dzinējs:variants", OCR teksts)."""
        truths = truth_digits(field, value)
        if not truths:
            return
        self.samples += 1
        self.by_field[field] += 1
        if field == "serial":
            for t in truths:
                self.first_true[t[0]] += 1
        for source, text in readings:
            engine = source.split(":")[0]
            pairs = aligned_pairs(text, truths)
            for raw_c, true_c in pairs:
                self.counts[engine][raw_c][true_c] += 1
            if field == "serial" and pairs:
                self.first_seen[parsing.to_digits(pairs[0][0])][pairs[0][1]] += 1

    def table(self, engine: str) -> dict[str, str]:
        out = {}
        for raw_c, counter in self.counts.get(engine, {}).items():
            total = sum(counter.values())
            digit, n = counter.most_common(1)[0]
            if total >= MIN_COUNT and n / total >= MIN_SHARE:
                out[raw_c] = digit
        return out

    def first_digit_table(self) -> dict[str, str]:
        """Pirmie cipari, kas sērijas numuros nekad nav sastopami (piem. 7), un ar ko
        OCR tos visbiežāk sajauc (piem. 1)."""
        total = sum(self.first_true.values())
        if total < 30:
            return {}
        out = {}
        for digit in "0123456789":
            if self.first_true[digit] / total < 0.01 and self.first_seen.get(digit):
                true_counter = Counter({d: n for d, n in self.first_seen[digit].items() if d != digit})
                if true_counter:
                    out[digit] = true_counter.most_common(1)[0][0]
        return out

    def tables(self) -> dict:
        out: dict = {engine: self.table(engine) for engine in self.counts}
        first = self.first_digit_table()
        if first:
            out["_first"] = first
        return out


def readings_path(png: Path) -> Path:
    return png.with_suffix(".json")


def save_readings(png: Path, readings: list[tuple[str, str]]) -> None:
    readings_path(png).write_text(json.dumps(readings, ensure_ascii=False), encoding="utf-8")


def load_corrections(samples_dir: Path) -> Corrections:
    """Ielasa visus paraugus, kuriem ir saglabāti OCR nolasījumi."""
    corr = Corrections()
    for field in ("serial", "date"):
        for js in sorted((samples_dir / field).glob("*.json")):
            value = js.stem.split("__")[0]
            try:
                readings = [tuple(r) for r in json.loads(js.read_text(encoding="utf-8"))]
            except (OSError, ValueError):
                continue
            corr.add(field, value, readings)
    return corr


def missing_readings(samples_dir: Path) -> list[tuple[str, Path]]:
    """Paraugi bez OCR nolasījumiem (piem. saglabāti ar vecāku versiju)."""
    out = []
    for field in ("serial", "date"):
        for png in sorted((samples_dir / field).glob("*.png")):
            if not readings_path(png).exists():
                out.append((field, png))
    return out


def apply(text: str, table: Optional[dict[str, str]]) -> str:
    """Pārvērš iemācītos simbolus ciparos (pirms parastās pārvēršanas)."""
    if not table:
        return text
    return "".join(table.get(ch, ch) for ch in text)
