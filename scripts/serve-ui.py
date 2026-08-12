#!/usr/bin/env python3
"""Serve the built classroom UI. This is the production/kiosk path.

`pnpm dev` is a development convenience: it needs node_modules, a package
manager, a filesystem watcher and ~400 MB of RAM to serve files that were
already built. On the appliance we serve `apps/classroom-ui/dist` with the
Python standard library and nothing else.

Two things a plain `python3 -m http.server` gets wrong here:

1. The UI is a single-page app. `/classroom` and `/control` are *routes*, not
   files. Without an index.html fallback the kiosk shows a 404 on boot.
2. Live2D ships `.moc3`, `.moc3`-adjacent binaries and `.zip` model bundles.
   Served with the wrong Content-Type some of those are rejected by the
   browser and the avatar silently never appears.

Also exposes `GET /__health` so the boot health gate (scripts/wait-healthy.sh)
can treat every Bright service identically.

    ./scripts/serve-ui.py --root apps/classroom-ui/dist --port 3000

Binds 127.0.0.1 by default and refuses to bind anything else unless
BRIGHT_ALLOW_EXTERNAL_BIND=1 is set. Nothing in this system should ever be
reachable from the school's network.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import posixpath
import sys
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Types the stdlib table does not know about, or gets wrong on some distros.
EXTRA_TYPES = {
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".json": "application/json",
    ".wasm": "application/wasm",
    ".zip": "application/zip",
    ".moc3": "application/octet-stream",
    ".model3": "application/json",
    ".exp3": "application/json",
    ".motion3": "application/json",
    ".physics3": "application/json",
    ".pose3": "application/json",
    ".map": "application/json",
    ".woff2": "font/woff2",
}
for _ext, _type in EXTRA_TYPES.items():
    mimetypes.add_type(_type, _ext)

# Hashed build assets are immutable; index.html must never be cached or an
# update leaves the kiosk pinned to the previous release until someone clears
# the browser profile -- and nobody is there to do that.
IMMUTABLE_PREFIX = "/assets/"


class UIHandler(SimpleHTTPRequestHandler):
    root: Path

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(self.root), **kwargs)

    # ---------------------------------------------------------------- routing
    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] == "/__health":
            return self._health()
        return super().do_GET()

    def do_HEAD(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] == "/__health":
            return self._health(body=False)
        return super().do_HEAD()

    def _health(self, body: bool = True) -> None:
        payload = json.dumps(
            {"status": "ok", "service": "ui", "root": str(self.root)}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if body:
            self.wfile.write(payload)

    def translate_path(self, path: str) -> str:
        """Map a URL to a file, falling back to index.html for SPA routes."""
        clean = urllib.parse.urlsplit(path).path
        clean = posixpath.normpath(urllib.parse.unquote(clean))
        parts = [p for p in clean.split("/") if p not in ("", ".", "..")]
        target = self.root.joinpath(*parts)

        if target.is_dir():
            index = target / "index.html"
            if index.is_file():
                return str(index)
        if target.is_file():
            return str(target)

        # Unknown path. A missing asset should 404 honestly; an unknown *route*
        # is the SPA's business. Anything with a file extension is an asset.
        if parts and "." in parts[-1]:
            return str(target)
        return str(self.root / "index.html")

    def end_headers(self) -> None:
        path = self.path.split("?", 1)[0]
        if path.startswith(IMMUTABLE_PREFIX):
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        else:
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    # ------------------------------------------------------------------ noise
    def log_message(self, fmt: str, *args) -> None:
        # journald keeps every line forever on a box nobody visits. Log errors
        # only; a 200 for a .js file is not information.
        if args and str(args[1]).startswith(("4", "5")):
            sys.stderr.write("ui: %s\n" % (fmt % args))


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main() -> int:
    ap = argparse.ArgumentParser(description="Serve the built Bright classroom UI.")
    ap.add_argument("--root", default=os.environ.get("UI_ROOT", "apps/classroom-ui/dist"))
    ap.add_argument("--host", default=os.environ.get("UI_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("UI_PORT", "3000")))
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    if not (root / "index.html").is_file():
        sys.stderr.write(
            f"\nThe classroom screen has not been built yet.\n"
            f"  Looked in: {root}\n"
            f"  What to do: run  cd apps/classroom-ui && pnpm install && pnpm build\n"
            f"  On an appliance this means the USB update did not finish — "
            f"re-run ./scripts/usb-update.sh\n\n"
        )
        return 2

    if args.host not in ("127.0.0.1", "localhost", "::1") and \
            os.environ.get("BRIGHT_ALLOW_EXTERNAL_BIND") != "1":
        sys.stderr.write(
            f"refusing to bind {args.host}: Bright is loopback-only by design.\n"
        )
        return 2

    handler = type("BoundUIHandler", (UIHandler,), {"root": root})
    with Server((args.host, args.port), handler) as httpd:
        sys.stderr.write(f"ui: serving {root} on http://{args.host}:{args.port}\n")
        sys.stderr.flush()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OSError as exc:
        sys.stderr.write(
            f"\nThe classroom screen could not start: {exc}\n"
            f"  What to do: something else is already using that port. "
            f"Run ./scripts/doctor.sh\n\n"
        )
        raise SystemExit(1)
