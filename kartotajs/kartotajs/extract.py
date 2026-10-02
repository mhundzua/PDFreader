"""Lauku nolasīšana no ROVICO servisa līguma kvīts.

Veidlapa vienmēr ir viena un tā pati, tāpēc:
1. OCR atrod drukātās etiķetes (tās nolasās droši) un pēc tām aprēķina,
   kā šis skenējums ir mērogots un nobīdīts pret paraugu (TEMPLATE_*).
2. Katram laukam izgriežam apgabalu, kur tas ir ierakstīts.
3. Izgriezumu nolasām vairākos veidos (ar visiem pieejamajiem OCR dzinējiem,
   oriģinālu un tikai zilo tinti), un rezultātus apvienojam balsojumā.
"""

from __future__ import annotations

import base64
import datetime as dt
import io
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

from . import parsing
from .documents import page_count, render_page
from .ocr import Word

log = logging.getLogger(__name__)

# Parauga kvīts izmērs pikseļos un etiķešu augšējie kreisie stūri tajā.
TEMPLATE_SIZE = (1842, 1298)
TEMPLATE_ANCHORS = {
    "LIGUMANR": (1199, 57),
    "DATUMS": (1196, 146),  # augšējais; apakšējo "DATUMS" atfiltrējam
    "VIETA": (1200, 198),
    "IERICESKOMPLEKTACIJA": (1199, 254),
    "KONTAKTTALRUNIS": (59, 339),
    "ALKOMETRAMODELIS": (62, 389),
    "ALKOMETRASERIJASNR": (59, 429),
    "KVALITATESHOLOGRAMMAS": (63, 478),
    "SERVISAPIEZIMES": (1198, 393),
    "VEIKTOMERIJUMUSKAITS": (60, 531),
    "CENA": (1197, 717),
    "SERVISADARBUVEICEJS": (1193, 762),
    "IERICESPIENEMEJS": (1199, 908),
}
# Lauku apgabali parauga koordinātās: x0, y0, x1, y1.
TEMPLATE_FIELDS = {
    "contract": (1430, 35, 1810, 120),
    "date": (1330, 115, 1810, 205),
    "serial": (420, 395, 1000, 485),
}
FIELD_LABELS = {"contract": "LIGUMANR", "date": "DATUMS", "serial": "ALKOMETRASERIJASNR"}

RENDER_DPI = 200


@dataclass
class FieldResult:
    value: str = ""
    confident: bool = False
    note: str = ""
    crop_png: str = ""  # base64
    candidates: list[str] = field(default_factory=list)
    second: str = ""  # otrs sērijas Nr., ja kvītī ir divi alkometri

    def as_dict(self) -> dict:
        return {
            "value": self.value,
            "confident": self.confident,
            "note": self.note,
            "crop": self.crop_png,
            "candidates": self.candidates,
            "second": self.second,
        }


def png_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


# --- izvietojums ------------------------------------------------------------

def fit_layout(words: list[Word], size: tuple[int, int]) -> tuple[np.ndarray, int]:
    """Aprēķina afīnu pārveidi no parauga koordinātām uz šī attēla koordinātām.

    Atgriež (3x2 matrica, atrasto etiķešu skaits). Ja etiķetes netika atrastas,
    izmanto vienkāršu mērogošanu pēc attēla izmēra.
    """
    width, height = size
    src, dst = [], []
    for w in words:
        norm = parsing.ascii_upper(w.text)
        for label, point in TEMPLATE_ANCHORS.items():
            if not parsing.label_length(norm, label):
                continue
            # Veidlapas apakšā ir vēl viens "DATUMS" - tas nav mums vajadzīgais.
            if label == "DATUMS" and w.box[1] > height * 0.4:
                continue
            src.append(point)
            dst.append(w.box[:2])
            break
    src_arr, dst_arr = np.array(src, float), np.array(dst, float)
    # Atkārtoti aprēķinām, katru reizi atmetot sliktāk atbilstošo etiķeti.
    while len(src_arr) >= 3:
        a = np.c_[src_arr, np.ones(len(src_arr))]
        matrix, *_ = np.linalg.lstsq(a, dst_arr, rcond=None)
        residual = np.linalg.norm(a @ matrix - dst_arr, axis=1)
        worst = int(residual.argmax())
        if residual[worst] <= max(15.0, width * 0.01):
            if _plausible(matrix, size):
                return matrix, len(src_arr)
            break
        src_arr = np.delete(src_arr, worst, axis=0)
        dst_arr = np.delete(dst_arr, worst, axis=0)
    sx = width / TEMPLATE_SIZE[0]
    sy = height / TEMPLATE_SIZE[1]
    return np.array([[sx, 0.0], [0.0, sy], [0.0, 0.0]]), len(src)


def _plausible(matrix: np.ndarray, size: tuple[int, int]) -> bool:
    """Atmet nepareizi aprēķinātu pārveidi (piem., ja kāda etiķete atrasta kļūdaini)."""
    sx, sy = matrix[0, 0], matrix[1, 1]
    expected = size[0] / TEMPLATE_SIZE[0]
    return 0.5 * expected < sx < 2 * expected and 0.5 * expected < sy < 2 * expected


def to_image(matrix: np.ndarray, x: float, y: float) -> tuple[float, float]:
    px, py = np.array([x, y, 1.0]) @ matrix
    return float(px), float(py)


def field_box(matrix: np.ndarray, name: str, size: tuple[int, int]) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = TEMPLATE_FIELDS[name]
    ax, ay = to_image(matrix, x0, y0)
    bx, by = to_image(matrix, x1, y1)
    return (
        max(0, int(min(ax, bx))), max(0, int(min(ay, by))),
        min(size[0], int(max(ax, bx))), min(size[1], int(max(ay, by))),
    )


# --- attēlu sagatavošana -----------------------------------------------------

def blue_ink(img: Image.Image) -> np.ndarray:
    """Cik "zils" ir katrs pikselis (0..255). Drukātais teksts un līnijas ir melni."""
    a = np.asarray(img.convert("RGB")).astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return np.clip((b - r - 10) * 4, 0, 255).astype(np.uint8)


def ink_only(img: Image.Image) -> Image.Image:
    """Melna zilā tinte uz balta fona."""
    return Image.fromarray(255 - blue_ink(img)).convert("RGB")


def ink_line(img: Image.Image) -> Optional[tuple[int, int, int, int]]:
    """Atrod blīvāko ar roku rakstīto rindu izgriezumā (x0, y0, x1, y1)."""
    mask = blue_ink(img) > 60
    rows = np.where(mask.sum(1) > 2)[0]
    if len(rows) == 0:
        return None
    runs, start, prev = [], rows[0], rows[0]
    for y in rows[1:]:
        if y - prev > 6:
            runs.append((start, prev))
            start = y
        prev = y
    runs.append((start, prev))
    y0, y1 = max(runs, key=lambda r: mask[r[0]:r[1] + 1].sum())
    cols = np.where(mask[y0:y1 + 1].sum(0) > 0)[0]
    pad = 8
    return (
        max(0, int(cols.min()) - pad), max(0, int(y0) - pad),
        min(img.width, int(cols.max()) + pad), min(img.height, int(y1) + pad),
    )


# --- lauku nolasīšana -------------------------------------------------------

def _strip_label(text: str, label: str) -> str:
    """No 'LIGUMANr.: ROV_043274' atstāj tikai vērtību."""
    size = parsing.label_length(parsing.ascii_upper(text), label)
    if not size:
        return text
    # Atrodam, kur oriģinālajā tekstā beidzas etiķete (ņemot vērā izlaistos simbolus).
    count = 0
    for i, ch in enumerate(text):
        if parsing.ascii_upper(ch):
            count += 1
        if count >= size:
            rest = text[i + 1:]
            return rest.lstrip(" .:")
    return ""


def _overlap(a, b) -> float:
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return (x1 - x0) * (y1 - y0) / max(1.0, (a[2] - a[0]) * (a[3] - a[1]))


def collect_texts(name: str, page: Image.Image, page_words: dict, box, engines) -> list[tuple[str, float, str]]:
    """Visi teksta varianti laukam: (teksts, ticamība, avots)."""
    texts = []
    label = FIELD_LABELS[name]
    for eng_name, words in page_words.items():
        for w in words:
            norm = parsing.ascii_upper(w.text)
            if parsing.label_length(norm, label):
                # OCR mēdz etiķeti un vērtību nolasīt kā vienu rindu.
                if label == "DATUMS" and w.box[1] > page.height * 0.4:
                    continue
                rest = _strip_label(w.text, label)
                if rest:
                    texts.append((rest, w.conf, f"{eng_name}:lapa"))
            elif _overlap(w.box, box) > 0.5:
                texts.append((w.text, w.conf, f"{eng_name}:lapa"))
                texts.extend((a, w.conf * 0.8, f"{eng_name}:lapa-alt") for a in w.alts)

    crop = page.crop(box)
    variants = [("izgriezums", crop), ("tinte", ink_only(crop))]
    line = ink_line(crop)
    if line and name != "contract":
        tight = crop.crop(line)
        variants += [("rinda", tight), ("rinda-tinte", ink_only(tight))]
    for eng in engines:
        for var_name, img in variants:
            if name == "contract" and var_name != "izgriezums":
                continue  # līguma Nr. ir drukāts melnā krāsā
            try:
                if var_name.startswith("rinda"):
                    words = eng.read_line(img)
                else:
                    big = img.resize((img.width * 2, img.height * 2))
                    words = sorted(eng.read(big), key=lambda w: w.box[0])
            except Exception as exc:
                log.warning("OCR kļūda (%s, %s): %s", eng.name, var_name, exc)
                continue
            if words:
                joined = " ".join(w.text for w in words)
                conf = float(np.mean([w.conf for w in words]))
                texts.append((joined, conf, f"{eng.name}:{var_name}"))
                for w in words:
                    texts.extend((a, w.conf * 0.8, f"{eng.name}:{var_name}-alt") for a in w.alts)
    return texts


def _vote(parsed: list[tuple[str, float, str]]) -> tuple[str, int, int, list[str]]:
    """Atgriež (labākā vērtība, cik avotu to atbalsta, cik dažādu OCR dzinēju to atbalsta,
    visi varianti)."""
    scores: dict[str, float] = defaultdict(float)
    sources: dict[str, set] = defaultdict(set)
    for value, conf, src in parsed:
        scores[value] += conf
        sources[value].add(src.split("-alt")[0])
    if not scores:
        return "", 0, 0, []
    ranked = sorted(scores, key=lambda v: (-len(sources[v]), -scores[v]))
    best = ranked[0]
    engines = {s.split(":")[0] for s in sources[best]}
    return best, len(sources[best]), len(engines), ranked[:5]


def _conflicts(best: str, ranked: list[str]) -> bool:
    """Vai ir cits tikpat garš variants ar atšķirīgu vērtību (piem., 229604 pret 429604)."""
    return any(v != best and len(v) == len(best) for v in ranked)


def _second_serial(best: str, texts: list[tuple[str, float, str]]) -> str:
    """Otrs sērijas Nr., ja kādā nolasījumā blakus labākajam ir vēl viens numurs."""
    votes: dict[str, float] = defaultdict(float)
    for text, conf, _ in texts:
        serials = parsing.find_serials(text)
        if best not in serials:
            continue
        for other in serials:
            if other != best and len(other) >= 5 and other not in best and best not in other:
                votes[other] += conf
    return max(votes, key=votes.get) if votes else ""


def read_field(name: str, page: Image.Image, page_words: dict, matrix, engines) -> FieldResult:
    box = field_box(matrix, name, page.size)
    crop = page.crop(box)
    texts = collect_texts(name, page, page_words, box, engines)
    result = FieldResult(crop_png=png_b64(crop))

    parsed = []
    for text, conf, src in texts:
        if name == "contract":
            value = parsing.find_contract(text)
        elif name == "serial":
            value = parsing.find_serial(text)
        else:
            d = parsing.find_date(text)
            value = d.isoformat() if d else None
        if value:
            parsed.append((value, conf, src))

    if name == "date" and not parsed:
        for text, conf, src in texts:
            d = parsing.find_day_month(text)
            if d:
                parsed.append((d.isoformat(), conf, src))
        if parsed:
            result.note = "Gads nav salasāms, pieņemts pēdējais iespējamais. Pārbaudiet datumu"

    best, support, engine_support, ranked = _vote(parsed)
    result.value = best
    result.candidates = ranked
    if not best:
        result.note = "Neizdevās nolasīt, lūdzu ierakstiet"
        return result

    if name == "contract":
        result.confident = len(ranked) == 1
    else:
        # Rokraksts: viens OCR dzinējs var konsekventi kļūdīties (piem., rokraksta '2'
        # vienmēr nolasīt kā '4'), tāpēc drošs tikai tad, ja vismaz divi dažādi dzinēji
        # neatkarīgi nonāk pie tās pašas vērtības un nav pretrunīgu variantu.
        result.confident = (support >= 3 and engine_support >= 2
                            and not _conflicts(best, ranked) and not result.note)
        if name == "serial":
            result.second = _second_serial(best, texts)
            if result.second:
                result.confident = False
                result.note = "Atrasti divi sērijas numuri (divi alkometri?), pārbaudiet abus"
            elif len(best) != 6:
                result.confident = False
                result.note = "Numurs nav 6 cipari, lūdzu pārbaudiet"
    if not result.confident and not result.note:
        result.note = "Rīks nav pārliecināts, lūdzu pārbaudiet"
    return result


def find_receipts(words: list[Word], size: tuple[int, int]) -> list[tuple[int, int]]:
    """Atrod, cik kvīšu ir lapā (piem. divas uz skenera stikla viena virs otras).

    Katrai kvītij augšā ir "ROVICO" logo un "LĪGUMA Nr." etiķete. Atgriež katras
    kvīts augšējo un apakšējo robežu pikseļos.
    """
    _, height = size
    marks = sorted(
        w.box[1] for w in words
        if parsing.ascii_upper(w.text) == "ROVICO"
        or parsing.label_length(parsing.ascii_upper(w.text), "LIGUMANR")
    )
    groups: list[list[float]] = []
    for y in marks:
        if groups and y - groups[-1][-1] < height * 0.15:
            groups[-1].append(y)
        else:
            groups.append([y])
    if len(groups) <= 1:
        return [(0, height)]
    pad = int(height * 0.02)
    cuts = [0] + [max(0, int(min(g)) - pad) for g in groups[1:]] + [height]
    return [(cuts[i], cuts[i + 1]) for i in range(len(groups))]


def _shift(words: list[Word], y0: int, y1: int) -> list[Word]:
    """Vārdi, kas pieder kvītij starp y0 un y1, ar koordinātām attiecībā pret to."""
    out = []
    for w in words:
        cy = (w.box[1] + w.box[3]) / 2
        if y0 <= cy < y1:
            box = (w.box[0], w.box[1] - y0, w.box[2], w.box[3] - y0)
            out.append(Word(w.text, w.conf, box, list(w.alts)))
    return out


def read_receipt(img: Image.Image, page_words: dict, engines) -> dict:
    all_words = [w for ws in page_words.values() for w in ws]
    matrix, anchors = fit_layout(all_words, img.size)
    fields = {
        name: read_field(name, img, page_words, matrix, engines).as_dict()
        for name in ("contract", "serial", "date")
    }
    return {"fields": fields, "anchors": anchors}


def extract_page(path: Path, page_index: int, engines) -> dict:
    """Nolasa vienu faila lapu. Atgriež visas tajā atrastās kvītis ("units")."""
    page = render_page(path, page=page_index)
    page_words = {}
    for eng in engines:
        try:
            page_words[eng.name] = eng.read(page)
        except Exception as exc:
            log.warning("OCR kļūda (%s): %s", eng.name, exc)
    all_words = [w for ws in page_words.values() for w in ws]
    units = []
    for i, (y0, y1) in enumerate(find_receipts(all_words, page.size)):
        img = page.crop((0, y0, page.width, y1))
        words = {name: _shift(ws, y0, y1) for name, ws in page_words.items()}
        unit = read_receipt(img, words, engines)
        unit.update({
            "id": f"{page_index}-{i}",
            "page": page_index,
            # robežas kā daļa no lapas augstuma (neatkarīgi no izšķirtspējas)
            "top": round(y0 / page.height, 4),
            "bottom": round(y1 / page.height, 4),
        })
        units.append(unit)
    return {
        "page": page_index,
        "units": units,
        "engines": [e.name for e in engines],
        "extracted_at": dt.datetime.now().isoformat(timespec="seconds"),
    }


def extract(path: Path, engines) -> dict:
    """Ērtības funkcija: pirmās lapas pirmā kvīts (un visas kvītis laukā "units")."""
    result = extract_page(path, 0, engines)
    first = result["units"][0]
    return {**result, "fields": first["fields"], "anchors": first["anchors"],
            "pages": page_count(path)}
