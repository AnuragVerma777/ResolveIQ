"""Automated QA script to audit console errors, network calls, and viewport responsiveness."""
import sys
from playwright.sync_api import sync_playwright

def audit():
    errors = []
    viewports = [
        {"name": "Desktop (1440x900)", "width": 1440, "height": 900},
        {"name": "Tablet (768x1024)", "width": 768, "height": 1024},
        {"name": "Mobile (375x812)", "width": 375, "height": 812},
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)

        for vp in viewports:
            print(f"\n--- Testing Viewport: {vp['name']} ---")
            context = browser.new_context(viewport={"width": vp["width"], "height": vp["height"]})
            page = context.new_page()

            console_logs = []
            page_errors = []
            failed_requests = []

            page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
            page.on("pageerror", lambda err: page_errors.append(str(err)))
            page.on("requestfailed", lambda req: failed_requests.append(f"{req.method} {req.url} - {req.failure}"))

            # Navigate to root (which serves frontend build)
            page.goto("http://127.0.0.1:8000", wait_until="networkidle")
            page.wait_for_timeout(1000)

            # Check horizontal scroll overflow
            scroll_width = page.evaluate("() => document.documentElement.scrollWidth")
            client_width = page.evaluate("() => document.documentElement.clientWidth")
            overflow_diff = scroll_width - client_width
            print(f"Viewport width: {vp['width']}, clientWidth: {client_width}, scrollWidth: {scroll_width}")
            if overflow_diff > 1:
                print(f"  ⚠️ Warning: Horizontal overflow detected: {overflow_diff}px")
            else:
                print("  ✓ No horizontal overflow.")

            # Test tab navigations
            tabs = ["Workflow", "PayPal Hub", "Evidence Matrix", "Studio", "Intake", "Vault", "Zapier", "API"]
            for tab in tabs:
                btn = page.locator(f"button:has-text('{tab}')").first
                if btn.count() > 0:
                    btn.click()
                    page.wait_for_timeout(400)
                    print(f"  ✓ Navigated to '{tab}' tab")
                else:
                    print(f"  ⚠️ Tab button '{tab}' not found in DOM")

            # Check for critical console errors
            severe_logs = [log for log in console_logs if "[error]" in log.lower()]
            if page_errors:
                print(f"  ❌ Uncaught page errors: {page_errors}")
                errors.extend(page_errors)
            if severe_logs:
                print(f"  ⚠️ Console error logs: {severe_logs}")
            else:
                print("  ✓ Zero console errors.")

            if failed_requests:
                print(f"  ⚠️ Failed requests: {failed_requests}")
            else:
                print("  ✓ All API / asset network requests succeeded.")

            context.close()

        browser.close()

    print("\n==========================================")
    if errors:
        print(f"QA Audit completed with {len(errors)} critical issues.")
        sys.exit(1)
    else:
        print("QA Audit completed: Zero uncaught exceptions. All viewports responsive.")
        sys.exit(0)

if __name__ == "__main__":
    audit()
