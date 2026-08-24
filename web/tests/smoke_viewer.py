#!/usr/bin/env python3
"""Headless browser smoke test for a built MSI viewer distribution."""

from __future__ import annotations

import argparse
import contextlib
import functools
import http.server
import threading
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".wasm": "application/wasm",
        ".whl": "application/zip",
    }

    def log_message(self, format, *args):  # noqa: A002
        pass


@contextlib.contextmanager
def serve(directory: Path):
    handler = functools.partial(QuietHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("distribution", type=Path)
    parser.add_argument("--timeout", type=int, default=180_000, help="Timeout in milliseconds")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    distribution = args.distribution.resolve()
    if not (distribution / "index.html").is_file():
        raise SystemExit(f"Not a built viewer directory: {distribution}")

    blocked_requests = []
    page_errors = []
    with serve(distribution) as base_url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        local_origin = urlparse(base_url).netloc

        page.add_init_script(
            """
            window.__pymsiSmokeErrors = [];
            window.addEventListener('pymsi-viewer-error', event => {
              const detail = event.detail || {};
              const error = detail.error || {};
              window.__pymsiSmokeErrors.push({
                phase: detail.phase || 'unknown',
                filename: detail.filename || null,
                message: error.message || String(error)
              });
            });
            """
        )

        def route_request(route):
            parsed = urlparse(route.request.url)
            if parsed.scheme in ("http", "https") and parsed.netloc != local_origin:
                blocked_requests.append(route.request.url)
                route.abort()
            else:
                route.continue_()

        page.route("**/*", route_request)
        page.on("pageerror", lambda error: page_errors.append(str(error)))

        try:
            page.goto(base_url, wait_until="domcontentloaded", timeout=args.timeout)
            page.wait_for_function(
                """
                window.__pymsiSmokeErrors.length > 0 ||
                document.querySelector('#load-example-file-button')?.disabled === false
                """,
                timeout=args.timeout,
            )
            initialization_errors = page.evaluate("window.__pymsiSmokeErrors")
            if initialization_errors:
                raise AssertionError(f"Viewer initialization errors: {initialization_errors}")

            page.evaluate("document.documentElement.dataset.theme = 'dark'")
            dark_background = page.locator("#msi-viewer-app").evaluate(
                "element => getComputedStyle(element).backgroundColor"
            )
            page.evaluate("document.documentElement.dataset.theme = 'light'")
            light_background = page.locator("#msi-viewer-app").evaluate(
                "element => getComputedStyle(element).backgroundColor"
            )
            if dark_background == light_background:
                raise AssertionError("Dark and light themes resolved to the same viewer background")

            page.locator("#load-example-file-button").click()
            page.wait_for_function(
                """
                window.__pymsiSmokeErrors.length > 0 ||
                (window.pymsiViewer?.currentMsi &&
                 window.pymsiViewer?.currentFileName === 'example.msi') ||
                document.querySelector('#loading-indicator')?.textContent.startsWith('Error')
                """,
                timeout=args.timeout,
            )
            load_errors = page.evaluate("window.__pymsiSmokeErrors")
            if load_errors:
                raise AssertionError(f"Viewer MSI loading errors: {load_errors}")
            if not page.evaluate("Boolean(window.pymsiViewer?.currentMsi)"):
                indicator = page.locator("#loading-indicator").inner_text()
                raise AssertionError(f"Example MSI was not loaded: {indicator}")
            page.wait_for_selector("#current-file-display", state="visible", timeout=args.timeout)

            current_file = page.locator("#current-file-display").inner_text()
            summary_text = page.locator("#summary-content").inner_text()
            table_options = page.locator("#table-selector option").count()
            version_text = page.locator("#pymsi-version-footer").inner_text()

            assert "example.msi" in current_file
            assert summary_text.strip()
            assert "Select an MSI file" not in summary_text
            assert table_options > 1
            assert version_text.startswith("pymsi version:")
        except PlaywrightError as error:
            raise AssertionError(f"Browser smoke test failed: {error}") from error
        finally:
            browser.close()

    if blocked_requests:
        raise AssertionError(
            "The bundled viewer attempted external runtime requests:\n" + "\n".join(blocked_requests)
        )
    if page_errors:
        raise AssertionError("Uncaught browser errors:\n" + "\n".join(page_errors))

    print(
        "Viewer smoke test passed: Pyodide initialized, example.msi loaded, "
        "tables/summary rendered, themes switched, and no external requests were made."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
