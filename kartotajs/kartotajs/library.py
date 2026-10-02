"""Failu darbības: rinda, akceptēšana, atsaukšana, žurnāls.

Nekas diskā netiek mainīts, kamēr lietotājs nav nospiedis "Akceptēt".
"""

from __future__ import annotations

import base64
import csv
import datetime as dt
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Optional

from .config import Config
from .documents import as_pdf_bytes, is_supported, unit_pdf_bytes
from .naming import file_name, folder_name, parse_iso, validate


class ActionError(Exception):
    """Kļūda, ko parādām lietotājam."""


def list_inbox(cfg: Config) -> list[str]:
    inbox = cfg.inbox_path
    if not inbox.is_dir():
        return []
    files = [p for p in inbox.iterdir() if p.is_file() and is_supported(p)
             and not p.name.startswith(".")]
    return [p.name for p in sorted(files, key=lambda p: (p.stat().st_mtime, p.name))]


def unsupported_in_inbox(cfg: Config) -> list[str]:
    """Faili mapē Ienākošie, kurus rīks nevar atvērt (lai lietotājs zina, kāpēc to nav sarakstā)."""
    inbox = cfg.inbox_path
    if not inbox.is_dir():
        return []
    return sorted(p.name for p in inbox.iterdir()
                  if p.is_file() and not p.name.startswith(".") and not is_supported(p))


def inbox_file(cfg: Config, name: str) -> Path:
    """Droši atrod failu "Ienākošie" mapē (bez iespējas izkļūt ārpus tās)."""
    if not name or name != Path(name).name or name.startswith("."):
        raise ActionError("Nederīgs faila nosaukums")
    path = cfg.inbox_path / name
    if not path.is_file():
        raise ActionError(f"Fails '{name}' vairs nav mapē Ienākošie")
    if not is_supported(path):
        raise ActionError(f"Fails '{name}' nav atbalstīta veida")
    return path


def target_for(cfg: Config, contract: str, serial: str, date_iso: str) -> dict:
    errors, warnings = validate(contract, serial, date_iso)
    result = {"errors": errors, "warnings": warnings, "folder": "", "file": "", "exists": False}
    date = parse_iso(date_iso)
    if date and "date" not in errors:
        result["folder"] = folder_name(date)
    if "contract" not in errors and "serial" not in errors:
        result["file"] = file_name(contract.strip(), serial.strip())
    if result["folder"] and result["file"]:
        result["exists"] = (cfg.output_path / result["folder"] / result["file"]).exists()
        if result["exists"]:
            errors["file"] = "Šāds fails mērķa mapē jau ir. Pārbaudiet numurus"
    return result


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _free_name(directory: Path, name: str) -> Path:
    """Ja fails ar tādu nosaukumu jau ir, pievieno ' (2)', ' (3)', ..."""
    candidate = directory / name
    stem, suffix = Path(name).stem, Path(name).suffix
    n = 2
    while candidate.exists():
        candidate = directory / f"{stem} ({n}){suffix}"
        n += 1
    return candidate


def _undo_path(cfg: Config) -> Path:
    return cfg.state_dir / "atsaukt.json"


def _load_undo(cfg: Config) -> list[dict]:
    path = _undo_path(cfg)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _save_undo(cfg: Config, stack: list[dict]) -> None:
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    _undo_path(cfg).write_text(json.dumps(stack[-50:], ensure_ascii=False, indent=2), encoding="utf-8")


def last_action(cfg: Config) -> Optional[dict]:
    stack = _load_undo(cfg)
    return stack[-1] if stack else None


def _log(cfg: Config, action: str, record: dict) -> None:
    path = cfg.log_path
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh, delimiter=";")
        if new:
            writer.writerow(["laiks", "darbība", "oriģināls", "līguma nr", "sērijas nr",
                             "datums", "saglabāts kā"])
        writer.writerow([
            dt.datetime.now().isoformat(sep=" ", timespec="seconds"), action,
            record["source"], record["contract"], record["serial"], record["date"],
            record["target"],
        ])


def _save_samples(cfg: Config, record: dict, crops: dict, values: dict) -> list[str]:
    """Saglabā apstiprināto lauku izgriezumus vēlākai rokraksta apmācībai."""
    saved = []
    for field in ("serial", "date"):
        data = crops.get(field)
        if not data:
            continue
        folder = cfg.state_dir / "paraugi" / field
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{values[field]}__{record['contract']}.png"
        try:
            path.write_bytes(base64.b64decode(data))
            saved.append(str(path))
        except (ValueError, OSError):
            continue
    return saved


def _progress_path(cfg: Config) -> Path:
    return cfg.state_dir / "progress.json"


def _load_progress(cfg: Config) -> dict:
    try:
        return json.loads(_progress_path(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_progress(cfg: Config, data: dict) -> None:
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    _progress_path(cfg).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _fingerprint(path: Path) -> str:
    """Faila "nospiedums" (izmērs + laiks), lai cits fails ar to pašu nosaukumu netiktu jaukts."""
    st = path.stat()
    return f"{st.st_size}:{int(st.st_mtime)}"


def done_units(cfg: Config, name: str) -> set[str]:
    """Kuras kvītis no šī faila jau ir akceptētas (ja failā ir vairākas kvītis)."""
    entry = _load_progress(cfg).get(name)
    path = cfg.inbox_path / name
    if not entry or not path.exists() or entry.get("size") != _fingerprint(path):
        return set()
    return set(entry.get("done", {}))


def _set_done(cfg: Config, name: str, size: str, unit_id: str, target: Optional[str]) -> None:
    data = _load_progress(cfg)
    entry = data.get(name)
    if not entry or entry.get("size") != size:
        entry = {"size": size, "done": {}}
    if target is None:
        entry["done"].pop(unit_id, None)
    else:
        entry["done"][unit_id] = target
    if entry["done"]:
        data[name] = entry
    else:
        data.pop(name, None)
    _save_progress(cfg, data)


def accept(cfg: Config, name: str, contract: str, serial: str, date_iso: str,
           crops: Optional[dict] = None, unit: Optional[dict] = None,
           all_units: Optional[list[str]] = None) -> dict:
    """Saglabā kvīti. unit = {"id", "page", "top", "bottom"}, ja failā ir vairākas kvītis;
    all_units = visu faila kvīšu id (lai zinātu, kad oriģinālu var pārvietot)."""
    source = inbox_file(cfg, name)
    contract, serial, date_iso = contract.strip(), serial.strip(), date_iso.strip()
    info = target_for(cfg, contract, serial, date_iso)
    if info["errors"]:
        raise ActionError("; ".join(info["errors"].values()))

    unit_id = unit["id"] if unit else None
    all_units = all_units or ([unit_id] if unit_id else [])
    if unit_id and unit_id in done_units(cfg, name):
        raise ActionError("Šī kvīts jau ir akceptēta")
    if unit:
        content = unit_pdf_bytes(source, unit["page"], unit["top"], unit["bottom"])
    else:
        content = as_pdf_bytes(source)  # attēls tiek pārvērsts PDF

    folder = cfg.output_path / info["folder"]
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / info["file"]
    # Izveidojam failu tikai tad, ja tāda vēl nav (nekad nepārrakstām).
    try:
        with target.open("xb") as dst:
            dst.write(content)
    except FileExistsError:
        raise ActionError("Šāds fails mērķa mapē jau ir. Pārbaudiet numurus") from None
    shutil.copystat(source, target)

    size = _fingerprint(source)
    finished = True
    if unit_id:
        _set_done(cfg, name, size, unit_id, str(target))
        finished = set(all_units) <= done_units(cfg, name)
    processed = None
    if finished:
        # Visas kvītis no šī faila ir apstrādātas: oriģinālu pārvietojam.
        cfg.processed_path.mkdir(parents=True, exist_ok=True)
        processed = _free_name(cfg.processed_path, source.name)
        shutil.move(str(source), str(processed))

    record = {
        "source": name,
        "unit": unit_id,
        "size": size,
        "processed": str(processed) if processed else None,
        "target": str(target),
        "sha256": _sha256(target),
        "contract": contract,
        "serial": serial,
        "date": date_iso,
        "time": dt.datetime.now().isoformat(timespec="seconds"),
    }
    record["samples"] = _save_samples(cfg, record, crops or {}, {"serial": serial, "date": date_iso})
    stack = _load_undo(cfg)
    stack.append(record)
    _save_undo(cfg, stack)
    _log(cfg, "akceptēts", record)
    return {"target": str(target), "folder": info["folder"], "file": info["file"],
            "warnings": info["warnings"], "finished": finished}


def undo(cfg: Config) -> dict:
    stack = _load_undo(cfg)
    if not stack:
        raise ActionError("Nav ko atsaukt")
    record = stack[-1]
    target = Path(record["target"])
    original = cfg.inbox_path / record["source"]
    processed = Path(record["processed"]) if record.get("processed") else None

    if processed:
        if original.exists():
            raise ActionError(f"Mapē Ienākošie jau ir fails '{record['source']}'")
        if not processed.exists():
            raise ActionError("Oriģinālais fails mapē Apstrādāti vairs nav atrodams")
    elif not original.exists():
        raise ActionError(f"Fails '{record['source']}' vairs nav mapē Ienākošie")
    if target.exists():
        if _sha256(target) != record["sha256"]:
            raise ActionError("Saglabātais fails pa to laiku ir mainīts, atsaukt nevar")
        target.unlink()
        try:
            target.parent.rmdir()  # tikai, ja mape palikusi tukša
        except OSError:
            pass
    if processed:
        shutil.move(str(processed), str(original))
    if record.get("unit"):
        _set_done(cfg, record["source"], record.get("size") or _fingerprint(original),
                  record["unit"], None)
    for sample in record.get("samples", []):
        try:
            os.remove(sample)
        except OSError:
            pass
    stack.pop()
    _save_undo(cfg, stack)
    _log(cfg, "atsaukts", record)
    return {"source": record["source"], "unit": record.get("unit")}
