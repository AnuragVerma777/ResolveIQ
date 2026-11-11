"""Playwright automated script to capture actual screenshots of ResolveIQ."""
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

SCREENSHOTS_DIR = Path("docs/screenshots")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        # Use a high-DPI desktop viewport for crisp text & badges
        context = browser.new_context(
            viewport={"width": 1440, "height": 920},
            device_scale_factor=1.5,
        )
        page = context.new_page()

        print("Navigating to ResolveIQ on http://127.0.0.1:8000...")
        page.goto("http://127.0.0.1:8000", wait_until="networkidle")
        time.sleep(2)

        # 1. Capture Command Center (PayPal Live Hub)
        print("Capturing Command Center (PayPal Hub)...")
        # Click PayPal Hub tab
        page.locator("button:has-text('PayPal Hub')").click()
        time.sleep(1.5)
        page.screenshot(path=str(SCREENSHOTS_DIR / "command-center.png"), full_page=False)

        # 2. Capture Dispute Investigation Workspace
        print("Capturing Dispute Investigation workspace...")
        page.locator("button:has-text('Intake')").click()
        time.sleep(2)
        page.screenshot(path=str(SCREENSHOTS_DIR / "dispute-investigation.png"), full_page=False)

        # 3. Capture Evidence Intelligence / Evidence Matrix
        print("Capturing Evidence Intelligence...")
        page.locator("button:has-text('Evidence Matrix')").click()
        time.sleep(2)
        # Also ensure matrix is generated or refreshed if needed
        page.screenshot(path=str(SCREENSHOTS_DIR / "evidence-matrix.png"), full_page=False)
        # Copy to evidence-intelligence.png as well for clarity
        page.screenshot(path=str(SCREENSHOTS_DIR / "evidence-intelligence.png"), full_page=False)

        # 4. Capture Resolution Studio
        print("Capturing Resolution Studio...")
        page.locator("button:has-text('Studio')").click()
        time.sleep(2)
        page.screenshot(path=str(SCREENSHOTS_DIR / "resolution-studio.png"), full_page=False)

        # 5. Capture Automation Settings
        print("Capturing Automation Settings...")
        page.locator("button:has-text('Zapier')").click()
        time.sleep(1.5)
        page.screenshot(path=str(SCREENSHOTS_DIR / "automation-settings.png"), full_page=False)

        # Bonus: Capture the Unified Workflow / Executive View
        print("Capturing Workflow Command Center...")
        page.locator("button:has-text('Workflow')").click()
        time.sleep(1.5)
        page.screenshot(path=str(SCREENSHOTS_DIR / "workflow-orchestration.png"), full_page=False)

        print("All screenshots successfully captured!")
        browser.close()

if __name__ == "__main__":
    run()
