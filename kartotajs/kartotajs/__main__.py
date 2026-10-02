"""Palaišana: python -m kartotajs [--port 8765] [--no-browser]"""

from __future__ import annotations

import argparse
import logging
import threading
import webbrowser

from .server import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Kvīšu kārtotājs")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="neatvērt pārlūku")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    app = create_app()
    url = f"http://127.0.0.1:{args.port}"
    print(f"\nKvīšu kārtotājs darbojas: {url}\nLai apturētu, aizveriet šo logu vai spiediet Ctrl+C.\n")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=args.port, threaded=True)


if __name__ == "__main__":
    main()
