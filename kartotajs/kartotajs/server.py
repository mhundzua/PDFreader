"""Lokālais tīmekļa serveris (tikai 127.0.0.1) ar saskarni pārlūkā."""

from __future__ import annotations

import io
import logging
import threading
import time
from pathlib import Path

import mimetypes

from flask import Flask, jsonify, request, send_file

from PIL import Image

from . import documents, extract, learning, library
from .config import Config
from .ocr import available_engines

log = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"


class Extractor:
    """Nolasa kvītis pa lapām un kešo rezultātus; fonā sagatavo nākamās."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self._engines = None
        self._engine_error = ""
        self._cache: dict[tuple, dict] = {}
        self._page_counts: dict[tuple, int] = {}
        self._lock = threading.Lock()
        self.corrections = learning.load_corrections(library.samples_dir(cfg))
        threading.Thread(target=self._background, daemon=True).start()

    def learn(self, field: str, value: str, readings: list) -> None:
        """Pēc akceptēšanas: nākamās kvītis jau lasām ar papildināto tabulu."""
        self.corrections.add(field, value, [tuple(r) for r in readings])

    def _bootstrap_samples(self) -> None:
        """Vecākiem paraugiem (bez OCR nolasījumiem) nolasījumus izveidojam vienreiz fonā."""
        missing = learning.missing_readings(library.samples_dir(self.cfg))
        if not missing:
            return
        log.info("Mācīšanās: sagatavoju %d paraugus", len(missing))
        for field, png in missing:
            if library.list_inbox(self.cfg) and any(
                    not self.cached(self.cfg.inbox_path / n, 0) for n in library.list_inbox(self.cfg)):
                return  # vispirms nolasām jaunās kvītis; turpināsim vēlāk
            try:
                with self._lock:
                    crop = Image.open(png).convert("RGB")
                    texts = extract.crop_texts(field, crop, self.engines())
                readings = [(src, text) for text, _, src in texts]
                learning.save_readings(png, readings)
                self.learn(field, png.stem.split("__")[0], readings)
            except Exception:
                log.exception("Neizdevās sagatavot paraugu %s", png.name)

    @staticmethod
    def _key(path: Path) -> tuple:
        st = path.stat()
        return (path.name, st.st_mtime_ns, st.st_size)

    def engines(self):
        if self._engines is None and not self._engine_error:
            try:
                self._engines = available_engines(self.cfg.ocr)
            except Exception as exc:
                self._engine_error = str(exc)
        if self._engine_error:
            raise RuntimeError(self._engine_error)
        return self._engines

    def pages(self, path: Path) -> int:
        key = self._key(path)
        if key not in self._page_counts:
            try:
                self._page_counts[key] = documents.page_count(path)
            except Exception:
                log.exception("Neizdevās atvērt %s", path.name)
                self._page_counts[key] = 1
        return self._page_counts[key]

    def cached(self, path: Path, page: int) -> bool:
        try:
            return (self._key(path), page) in self._cache
        except OSError:
            return False

    def get(self, path: Path, page: int) -> dict:
        key = (self._key(path), page)
        if key in self._cache:
            return self._cache[key]
        with self._lock:
            if key not in self._cache:
                started = time.time()
                try:
                    result = extract.extract_page(path, page, self.engines(),
                                                  self.corrections.tables())
                except Exception as exc:
                    log.exception("Neizdevās nolasīt %s", path.name)
                    result = {"error": f"Neizdevās nolasīt kvīti: {exc}", "page": page,
                              "units": [{"id": f"{page}-0", "page": page, "top": 0.0,
                                         "bottom": 1.0, "fields": {}}]}
                result["seconds"] = round(time.time() - started, 1)
                self._cache[key] = result
            return self._cache[key]

    def unit(self, path: Path, page: int, unit_id: str) -> dict:
        for unit in self.get(path, page)["units"]:
            if unit["id"] == unit_id:
                return unit
        raise library.ActionError("Šī kvīts failā vairs nav atrodama")

    def all_units(self, path: Path) -> list[str] | None:
        """Visu faila kvīšu id, ja visas lapas jau nolasītas; citādi None."""
        ids = []
        for page in range(self.pages(path)):
            if not self.cached(path, page):
                return None
            ids += [u["id"] for u in self.get(path, page)["units"]]
        return ids

    def _background(self) -> None:
        while True:
            try:
                for name in library.list_inbox(self.cfg):
                    path = self.cfg.inbox_path / name
                    for page in range(self.pages(path)):
                        if path.exists() and not self.cached(path, page):
                            self.get(path, page)
                self._bootstrap_samples()
            except Exception:
                log.exception("Fona nolasīšanas kļūda")
            time.sleep(2)


def queue_items(cfg: Config, extractor: Extractor) -> list[dict]:
    """Rinda pa kvītīm: failā var būt vairākas lapas un lapā vairākas kvītis."""
    items = []
    for name in library.list_inbox(cfg):
        path = cfg.inbox_path / name
        try:
            pages = extractor.pages(path)
        except OSError:
            continue
        done = library.done_units(cfg, name)
        for page in range(pages):
            page_label = f" · {page + 1}. lapa" if pages > 1 else ""
            if not extractor.cached(path, page):
                items.append({"key": f"{name}|{page}|", "name": name, "page": page,
                              "unit": None, "ready": False, "label": name + page_label})
                continue
            units = extractor.get(path, page)["units"]
            for i, unit in enumerate(units):
                if unit["id"] in done:
                    continue
                unit_label = f" · {i + 1}/{len(units)}" if len(units) > 1 else ""
                items.append({"key": f"{name}|{page}|{unit['id']}", "name": name, "page": page,
                              "unit": unit["id"], "ready": True,
                              "label": name + page_label + unit_label})
    return items


def create_app(cfg: Config | None = None) -> Flask:
    cfg = cfg or Config.load()
    cfg.ensure_dirs()
    app = Flask(__name__, static_folder=str(STATIC), static_url_path="/static")
    extractor = Extractor(cfg)
    app.config["extractor"] = extractor

    def error(message: str, status: int = 400):
        return jsonify({"error": message}), status

    @app.errorhandler(library.ActionError)
    def _action_error(exc):
        return error(str(exc), 409)

    @app.get("/")
    def index():
        return send_file(STATIC / "index.html")

    @app.get("/api/state")
    def state():
        return jsonify({
            "inbox": str(cfg.inbox_path),
            "output": str(cfg.output_path),
            "ocr": cfg.ocr,
            "queue": queue_items(cfg, extractor),
            "last": library.last_action(cfg),
            "unsupported": library.unsupported_in_inbox(cfg),
            "learned": extractor.corrections.by_field["serial"],
        })

    def _page_arg() -> int:
        try:
            return int(request.args.get("page", 0))
        except ValueError:
            return -1

    @app.get("/api/extract")
    def get_extract():
        path = library.inbox_file(cfg, request.args.get("name", ""))
        page = _page_arg()
        if not 0 <= page < extractor.pages(path):
            return error("Nav tādas lapas", 404)
        result = extractor.get(path, page)
        unit_id = request.args.get("unit") or ""
        done = library.done_units(cfg, path.name)
        units = [u for u in result["units"] if u["id"] not in done] or result["units"]
        unit = next((u for u in units if u["id"] == unit_id), units[0])
        return jsonify({**unit, "error": result.get("error", ""), "pages": extractor.pages(path),
                        "seconds": result.get("seconds")})

    @app.get("/api/page")
    def page_image():
        path = library.inbox_file(cfg, request.args.get("name", ""))
        page = _page_arg()
        if not 0 <= page < extractor.pages(path):
            return error("Nav tādas lapas", 404)
        img = extract.render_page(path, page=page, dpi=150)
        try:
            top = min(max(float(request.args.get("top", 0)), 0.0), 1.0)
            bottom = min(max(float(request.args.get("bottom", 1)), 0.0), 1.0)
        except ValueError:
            top, bottom = 0.0, 1.0
        if bottom - top > 0.05 and (top > 0 or bottom < 1):
            img = img.crop((0, int(top * img.height), img.width, int(bottom * img.height)))
        if img.width > 1800:
            img = img.resize((1800, round(img.height * 1800 / img.width)))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=88)
        buf.seek(0)
        return send_file(buf, mimetype="image/jpeg", max_age=0)

    @app.get("/api/pdf")
    def pdf():
        path = library.inbox_file(cfg, request.args.get("name", ""))
        if documents.is_image(path) and path.suffix.lower() in (".heic", ".heif", ".tif", ".tiff"):
            # Pārlūki šos formātus parasti neatver; rādām kā PDF.
            return send_file(io.BytesIO(documents.as_pdf_bytes(path)), mimetype="application/pdf")
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return send_file(path, mimetype=mime)

    @app.post("/api/target")
    def target():
        body = request.get_json(force=True) or {}
        return jsonify(library.target_for(
            cfg, body.get("contract", ""), body.get("serial", ""), body.get("date", "")))

    @app.post("/api/accept")
    def accept():
        body = request.get_json(force=True) or {}
        name = body.get("name", "")
        path = library.inbox_file(cfg, name)
        try:
            page = int(body.get("page", 0))
        except (TypeError, ValueError):
            return error("Nederīga lapa")
        if not 0 <= page < extractor.pages(path) or not extractor.cached(path, page):
            return error("Kvīts vēl nav nolasīta")
        unit = extractor.unit(path, page, body.get("unit") or f"{page}-0")
        all_units = extractor.all_units(path)
        crops = {k: v.get("crop", "") for k, v in unit.get("fields", {}).items()}
        readings = {k: v.get("readings", []) for k, v in unit.get("fields", {}).items()}
        result = library.accept(
            cfg, name, body.get("contract", ""), body.get("serial", ""), body.get("date", ""),
            crops,
            unit={"id": unit["id"], "page": page, "top": unit["top"], "bottom": unit["bottom"]},
            # Ja ne visas lapas vēl nolasītas, fails vēl nav pabeigts.
            all_units=all_units if all_units is not None else [unit["id"], "?"],
            readings=readings,
        )
        extractor.learn("serial", body.get("serial", "").strip(), readings.get("serial", []))
        extractor.learn("date", body.get("date", "").strip(), readings.get("date", []))
        return jsonify(result)

    @app.post("/api/undo")
    def undo():
        return jsonify(library.undo(cfg))

    @app.post("/api/settings")
    def settings():
        body = request.get_json(force=True) or {}
        inbox = (body.get("inbox") or "").strip()
        output = (body.get("output") or "").strip()
        if not inbox or not output:
            return error("Abām mapēm jābūt norādītām")
        if Path(inbox).expanduser().resolve() == Path(output).expanduser().resolve():
            return error("Ienākošo un kārtoto mapei jābūt dažādām")
        cfg.inbox, cfg.output = inbox, output
        cfg.save()
        cfg.ensure_dirs()
        return jsonify({"ok": True})

    return app
