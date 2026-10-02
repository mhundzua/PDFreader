"""Lokālais tīmekļa serveris (tikai 127.0.0.1) ar saskarni pārlūkā."""

from __future__ import annotations

import io
import logging
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, request, send_file

from . import extract, library
from .config import Config
from .ocr import available_engines

log = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"


class Extractor:
    """Nolasa laukus un kešo rezultātus; fonā sagatavo nākamās kvītis."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self._engines = None
        self._engine_error = ""
        self._cache: dict[tuple, dict] = {}
        self._lock = threading.Lock()
        threading.Thread(target=self._background, daemon=True).start()

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

    def cached(self, path: Path) -> bool:
        try:
            return self._key(path) in self._cache
        except OSError:
            return False

    def get(self, path: Path) -> dict:
        key = self._key(path)
        if key in self._cache:
            return self._cache[key]
        with self._lock:
            if key not in self._cache:
                started = time.time()
                try:
                    result = extract.extract(path, self.engines())
                except Exception as exc:
                    log.exception("Neizdevās nolasīt %s", path.name)
                    result = {"error": f"Neizdevās nolasīt kvīti: {exc}", "fields": {}}
                result["seconds"] = round(time.time() - started, 1)
                self._cache[key] = result
            return self._cache[key]

    def _background(self) -> None:
        while True:
            try:
                for name in library.list_inbox(self.cfg):
                    path = self.cfg.inbox_path / name
                    if path.exists() and not self.cached(path):
                        self.get(path)
            except Exception:
                log.exception("Fona nolasīšanas kļūda")
            time.sleep(2)


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
        names = library.list_inbox(cfg)
        return jsonify({
            "inbox": str(cfg.inbox_path),
            "output": str(cfg.output_path),
            "ocr": cfg.ocr,
            "queue": [{"name": n, "ready": extractor.cached(cfg.inbox_path / n)} for n in names],
            "last": library.last_action(cfg),
        })

    @app.get("/api/extract")
    def get_extract():
        path = library.inbox_file(cfg, request.args.get("name", ""))
        return jsonify(extractor.get(path))

    @app.get("/api/page")
    def page_image():
        path = library.inbox_file(cfg, request.args.get("name", ""))
        page = int(request.args.get("page", 0))
        if not 0 <= page < extract.page_count(path):
            return error("Nav tādas lapas", 404)
        img = extract.render_page(path, page=page, dpi=150)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=88)
        buf.seek(0)
        return send_file(buf, mimetype="image/jpeg", max_age=0)

    @app.get("/api/pdf")
    def pdf():
        path = library.inbox_file(cfg, request.args.get("name", ""))
        return send_file(path, mimetype="application/pdf")

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
        crops = {}
        if extractor.cached(path):
            fields = extractor.get(path).get("fields", {})
            crops = {k: v.get("crop", "") for k, v in fields.items()}
        result = library.accept(cfg, name, body.get("contract", ""), body.get("serial", ""),
                                body.get("date", ""), crops)
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
