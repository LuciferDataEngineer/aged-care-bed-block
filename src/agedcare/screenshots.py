"""Open the dashboard in a headless browser, switch every tab, and save screenshots."""

from __future__ import annotations

import subprocess
import sys
import time

from agedcare.paths import DOCS
from agedcare.sitebuild import build_site


def main() -> None:
    site = build_site()
    out = DOCS / "screenshots"
    out.mkdir(parents=True, exist_ok=True)
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", "8765", "--bind", "127.0.0.1"],
        cwd=site,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(0.8)
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 1100})
            page.goto("http://127.0.0.1:8765/", wait_until="networkidle")
            page.wait_for_selector("#kpis .kpi")
            page.add_style_tag(content=".topbar{position:static !important}")
            tabs = ["overview", "regions", "hospitals", "outlook", "action"]
            for tab in tabs:
                page.click(f'[data-tab="{tab}"]')
                page.wait_for_timeout(400)
                section = page.locator(f'[data-page="{tab}"]')
                assert section.is_visible()
                canvases = section.locator("canvas")
                count = canvases.count()
                for index in range(count):
                    box = canvases.nth(index).bounding_box()
                    assert box and box["width"] > 100 and box["height"] > 100, f"{tab} canvas {index} {box}"
                if tab == "regions":
                    assert page.locator("#map path").count() > 60
                    page.hover("#map path")
                    page.wait_for_timeout(200)
                page.screenshot(path=str(out / f"{tab}.png"), full_page=True)
            mobile = browser.new_page(viewport={"width": 390, "height": 844})
            mobile.goto("http://127.0.0.1:8765/", wait_until="networkidle")
            mobile.wait_for_selector("#kpis .kpi")
            mobile.add_style_tag(content=".topbar{position:static !important}")
            mobile.screenshot(path=str(out / "overview-mobile.png"), full_page=True)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
    print("screenshots in", out)


if __name__ == "__main__":
    main()
