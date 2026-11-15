#!/usr/bin/env python3
"""Render the reader in headless Chromium against a real local HTTP server.

file:// blocks pdf.js's worker, and the sandbox proxy blocks the CDN, so the
only honest way to exercise the render path is to serve the site from
127.0.0.1 and screenshot that.
"""
import http.server
import os
import json
import socketserver
import subprocess
import sys
import threading
from functools import partial
from pathlib import Path

ROOT = Path(os.environ.get("CE_TEST_ROOT", "/scratch/work/_mtest"))
PORT = 8765


def main():
    shards = ROOT / "data" / "shards.json"
    data = json.loads(shards.read_text())
    data[0]["cdn"] = f"http://127.0.0.1:{PORT}"
    data[0]["raw"] = f"http://127.0.0.1:{PORT}"
    shards.write_text(json.dumps(data, indent=1))

    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", PORT), handler)
    httpd.daemon_threads = True
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()

    results = []
    for width, slug, label in [
        (390, "pride-and-prejudice", "phone"),
        (820, "pride-and-prejudice", "tablet"),
        (390, "alice-in-wonderland", "phone-alice"),
    ]:
        page = ROOT / f"_t_{label}.html"
        html = (ROOT / "index.html").read_text()
        html = html.replace(
            "</body>",
            f'<script>setTimeout(function(){{openBook("{slug}")}},2200)</script></body>')
        page.write_text(html)
        out = f"/scratch/work/mob_{label}.png"
        subprocess.run([
            "chromium", "--headless=new", "--no-sandbox", "--disable-gpu",
            f"--window-size={width},844", "--virtual-time-budget=25000",
            f"--screenshot={out}", f"http://127.0.0.1:{PORT}/{page.name}",
        ], capture_output=True, timeout=200)
        results.append((label, width, out, Path(out).stat().st_size if Path(out).exists() else 0))
        page.unlink(missing_ok=True)

    httpd.shutdown()
    for r in results:
        print(f"{r[0]:<12} {r[1]:>4}px  {r[3]:>7} bytes  {r[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
