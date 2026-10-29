"""python -m ui: pornește serverul Green Proof și deschide pagina în browser."""

from __future__ import annotations

import argparse
import os
import threading
import webbrowser


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m ui", description="Interfața de demo Green Proof.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--fara-browser", action="store_true", help="nu deschide pagina automat")
    parser.add_argument(
        "--mod-extractie", choices=["real", "mock"], default="real",
        help="real: datele extrase din PDF-uri (_extras); mock: extras_mock.json (implicit: real)",
    )
    argumente = parser.parse_args()

    # config.py citește modul o singură dată, la import: se fixează înainte de a încărca serverul
    os.environ["MOD_EXTRACTIE"] = argumente.mod_extractie

    import uvicorn

    from ui.server import app

    adresa = f"http://{argumente.host}:{argumente.port}/"
    print(f"Green Proof: {adresa}  (Ctrl+C pentru oprire)")
    if not argumente.fara_browser:
        threading.Timer(1.0, webbrowser.open, args=(adresa,)).start()
    uvicorn.run(app, host=argumente.host, port=argumente.port, log_level="warning")


if __name__ == "__main__":
    main()
