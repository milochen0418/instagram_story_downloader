"""
診斷腳本：確認 Playwright 攔截 + in-page fetch reels_media 是否可行。
執行方式: poetry run python diag_archive.py
"""
import sys
import json
import yt_dlp
from playwright.sync_api import sync_playwright, Response

_BROWSERS = ["chrome", "firefox", "safari", "edge", "chromium"]


def extract_cookies(browser: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    ydl_opts = {"cookiesfrombrowser": (browser,), "quiet": True, "no_warnings": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for c in ydl.cookiejar:
            if "instagram.com" in getattr(c, "domain", ""):
                cookies[c.name] = c.value
    return cookies


def parse_ig_body(body: str) -> dict:
    """Handle Instagram's XSSI-protection prefix and payload wrapper."""
    if body.startswith("for (;;);"):
        body = body[9:]
    data = json.loads(body)
    return data.get("payload", data)


def main():
    # 1. Extract cookies
    cookies: dict[str, str] = {}
    for browser in _BROWSERS:
        try:
            print(f"Trying {browser}...", end=" ", flush=True)
            c = extract_cookies(browser)
            if "sessionid" in c:
                cookies = c
                print(f"OK ({len(c)} ig cookies)")
                break
            else:
                print(f"no sessionid")
        except Exception as e:
            print(f"error: {e}")

    if not cookies:
        print("ERROR: No Instagram session found.", file=sys.stderr)
        sys.exit(1)

    pw_cookies = [
        {"name": k, "value": v, "domain": ".instagram.com", "path": "/",
         "secure": True, "sameSite": "None",
         "httpOnly": k in ("sessionid", "ds_user_id")}
        for k, v in cookies.items()
    ]

    captured_day_shells: list[dict] = []
    captured_reels: dict[str, dict] = {}  # reel_id -> reel data

    with sync_playwright() as p:
        brow = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        ctx = brow.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        )
        ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )
        ctx.add_cookies(pw_cookies)
        page = ctx.new_page()

        def on_response(response: Response):
            url = response.url
            if "day_shells" in url:
                try:
                    body = response.body().decode("utf-8", errors="replace")
                    data = parse_ig_body(body)
                    items = data.get("items") or data.get("days") or []
                    captured_day_shells.extend(items)
                    print(f"  [intercept] day_shells → {len(items)} items")
                except Exception as e:
                    print(f"  [intercept] day_shells parse error: {e}")
            elif "reels_media" in url:
                try:
                    body = response.body().decode("utf-8", errors="replace")
                    data = parse_ig_body(body)
                    reels = data.get("reels") or {}
                    for reel_id, reel in reels.items():
                        captured_reels[reel_id] = reel
                    print(f"  [intercept] reels_media → {len(reels)} reels")
                except Exception as e:
                    print(f"  [intercept] reels_media parse error: {e}")

        page.on("response", on_response)

        print("\nNavigating to /archive/stories/ (networkidle)...", flush=True)
        page.goto(
            "https://www.instagram.com/archive/stories/",
            wait_until="networkidle",
            timeout=30000,
        )
        print(f"URL: {page.url}")
        print(f"After nav: {len(captured_day_shells)} day shells, {len(captured_reels)} reels")

        # Test in-page fetch for reels_media using an ID from the intercepted data
        if captured_day_shells:
            test_id = captured_day_shells[0].get("id", "")
            print(f"\nTest in-page fetch for reels_media with id={test_id!r}...")
            result = page.evaluate(
                f"""async () => {{
                    try {{
                        const r = await fetch(
                            '/api/v1/feed/reels_media/?reel_ids=' + encodeURIComponent('{test_id}'),
                            {{
                                credentials: 'include',
                                headers: {{
                                    'X-IG-App-ID': '936619743392459',
                                    'Accept': 'application/json, */*',
                                }}
                            }}
                        );
                        return {{status: r.status, ct: r.headers.get('content-type')||'', body: (await r.text()).substring(0,500)}};
                    }} catch(e) {{ return {{error: String(e)}}; }}
                }}"""
            )
            print(f"  status={result.get('status')}, ct={result.get('ct')}")
            print(f"  body[:200]: {result.get('body','')[:200]}")
            if result.get('error'):
                print(f"  error: {result['error']}")
        else:
            print("\nNo day_shells intercepted — not logged in?")

        brow.close()

    # Summary
    print("\n=== SUMMARY ===")
    print(f"day_shells intercepted: {len(captured_day_shells)}")
    if captured_day_shells:
        print("First 3 items:")
        for item in captured_day_shells[:3]:
            import datetime
            ts = item.get("timestamp", 0)
            dt = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else "?"
            print(f"  id={item.get('id')}, date={dt}, count={item.get('media_count')}")

    print(f"\nreels_media intercepted: {len(captured_reels)}")
    for rid, reel in list(captured_reels.items())[:2]:
        items = reel.get("items") or []
        print(f"  {rid}: {len(items)} media items")
        if items:
            mt = items[0].get("media_type")
            print(f"    first item media_type={mt}")


if __name__ == "__main__":
    main()

import sys
import json
import yt_dlp
from playwright.sync_api import sync_playwright, Response

_BROWSERS = ["chrome", "firefox", "safari", "edge", "chromium"]


def extract_cookies(browser: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    ydl_opts = {"cookiesfrombrowser": (browser,), "quiet": True, "no_warnings": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for c in ydl.cookiejar:
            if "instagram.com" in getattr(c, "domain", ""):
                cookies[c.name] = c.value
    return cookies


def main():
    # 1. Extract cookies
    cookies: dict[str, str] = {}
    used_browser = ""
    for browser in _BROWSERS:
        try:
            print(f"Trying cookies from {browser}...", end=" ", flush=True)
            c = extract_cookies(browser)
            if "sessionid" in c:
                cookies = c
                used_browser = browser
                print(f"OK ({len(c)} ig cookies)")
                break
            else:
                print(f"no sessionid ({len(c)} cookies)")
        except Exception as e:
            print(f"error: {e}")

    if not cookies:
        print("ERROR: No Instagram session found.", file=sys.stderr)
        sys.exit(1)

    # Convert to Playwright format
    pw_cookies = [
        {
            "name": k, "value": v,
            "domain": ".instagram.com", "path": "/",
            "secure": True, "sameSite": "None",
            "httpOnly": k in ("sessionid", "ds_user_id"),
        }
        for k, v in cookies.items()
    ]

    captured_calls: list[dict] = []

    with sync_playwright() as p:
        browser_pw = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        ctx = browser_pw.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )
        ctx.add_cookies(pw_cookies)
        page = ctx.new_page()

        # === Step 1: Verify login ===
        print("\nChecking login status...", flush=True)
        try:
            resp = page.request.get(
                "https://www.instagram.com/api/v1/accounts/current_user/?edit=true",
                headers={
                    "X-IG-App-ID": "936619743392459",
                    "X-Instagram-AJAX": "1",
                    "Accept": "application/json, */*",
                    "X-CSRFToken": cookies.get("csrftoken", ""),
                },
            )
            login_body = resp.text()
            print(f"  /current_user → status={resp.status} ct={resp.headers.get('content-type','')}")
            print(f"  body[:200]: {login_body[:200]}")
        except Exception as e:
            print(f"  /current_user error: {e}")

        # === Step 2: Intercept the archive page — let Instagram's own JS make the calls ===
        print("\nSetting up route interception on archive page...", flush=True)

        def on_response(response: Response):
            url = response.url
            if "archive" in url and "instagram.com" in url:
                try:
                    body = response.body().decode("utf-8", errors="replace")
                    captured_calls.append({
                        "url": url,
                        "status": response.status,
                        "ct": response.headers.get("content-type", ""),
                        "body": body[:800],
                    })
                    print(f"  CAPTURED: {url[:80]} → {response.status}")
                except Exception:
                    pass

        page.on("response", on_response)

        print("Navigating to /archive/stories/ ...", flush=True)
        page.goto(
            "https://www.instagram.com/archive/stories/",
            wait_until="networkidle",
            timeout=30000,
        )
        print(f"  URL: {page.url}, Title: {page.title()}")

        # Also try a direct day_shells call from inside the page (same origin, no CORS)
        print("\nMaking in-page fetch to day_shells ...", flush=True)
        in_page_result = page.evaluate(
            """async () => {
                try {
                    const r = await fetch(
                        '/api/v1/archive/reel/day_shells/?include_suggested_highlights=false&timezone_offset=0&initial_load=true',
                        {
                            credentials: 'include',
                            headers: {
                                'X-IG-App-ID': '936619743392459',
                                'X-ASBD-ID': '198387',
                                'Accept': 'application/json, */*',
                            }
                        }
                    );
                    return {status: r.status, ct: r.headers.get('content-type') || '', body: (await r.text()).substring(0,800)};
                } catch(e) { return {error: String(e)}; }
            }"""
        )
        print(f"  in-page fetch → status={in_page_result.get('status')}, "
              f"ct={in_page_result.get('ct')}, body_len={len(in_page_result.get('body',''))}")
        if in_page_result.get('body'):
            print(f"  body[:300]: {in_page_result['body'][:300]}")

        browser_pw.close()

    # === Results ===
    print("\n=== INTERCEPTED ARCHIVE CALLS ===")
    if not captured_calls:
        print("None. Instagram's page did not call archive API (or was not logged in).")
    for call in captured_calls:
        print(f"\nURL:  {call['url'][:100]}")
        print(f"Status: {call['status']}  CT: {call['ct']}")
        print(f"Body:   {call['body'][:400]}")
        try:
            data = json.loads(call['body'])
            items = data.get('items') or data.get('days') or []
            print(f"✅ Parsed JSON: keys={list(data.keys())}, items={len(items)}")
        except Exception:
            print("❌ Not valid JSON")


if __name__ == "__main__":
    main()

import sys
import json
import yt_dlp
from playwright.sync_api import sync_playwright

_BROWSERS = ["chrome", "firefox", "safari", "edge", "chromium"]
_IG_WEB_API = "https://www.instagram.com/api/v1"
_IG_APP_ID = "936619743392459"


def extract_cookies(browser: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    ydl_opts = {"cookiesfrombrowser": (browser,), "quiet": True, "no_warnings": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for c in ydl.cookiejar:
            if "instagram.com" in getattr(c, "domain", ""):
                cookies[c.name] = c.value
    return cookies


def main():
    # 1. Extract cookies
    cookies: dict[str, str] = {}
    used_browser = ""
    for browser in _BROWSERS:
        try:
            print(f"Trying cookies from {browser}...", end=" ", flush=True)
            c = extract_cookies(browser)
            if "sessionid" in c:
                cookies = c
                used_browser = browser
                print(f"OK ({len(c)} ig cookies)")
                print(f"  Cookie names: {sorted(cookies.keys())}")
                break
            else:
                print(f"no sessionid ({len(c)} cookies)")
        except Exception as e:
            print(f"error: {e}")

    if not cookies:
        print("ERROR: No Instagram session found in any browser.", file=sys.stderr)
        sys.exit(1)

    # 2. Convert to Playwright cookie format
    pw_cookies = []
    for name, value in cookies.items():
        pw_cookies.append({
            "name": name,
            "value": value,
            "domain": ".instagram.com",
            "path": "/",
            "secure": True,
            "httpOnly": name in ("sessionid", "ds_user_id"),
            "sameSite": "None",
        })

    # 3. Launch Playwright with stealth flags to bypass bot detection
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        # Hide webdriver detection
        ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        ctx.add_cookies(pw_cookies)
        page = ctx.new_page()

        # Navigate and wait for full load
        print("\nNavigating to instagram.com (networkidle)...", flush=True)
        page.goto("https://www.instagram.com/", wait_until="networkidle", timeout=30000)

        current_url = page.url
        title = page.title()
        print(f"URL after nav:  {current_url}")
        print(f"Page title:     {title}")

        # Check if cookies were applied
        pg_cookies = ctx.cookies("https://www.instagram.com")
        has_session = any(c["name"] == "sessionid" for c in pg_cookies)
        print(f"sessionid in browser: {has_session}  ({len(pg_cookies)} cookies total)\n")

        if "login" in current_url or "accounts" in current_url:
            print("WARNING: Navigated to login page — cookies might not be valid.")

        # Make the archive API call
        print("Calling archive/reel/day_shells/ via fetch()...", flush=True)
        result = page.evaluate(
            """async () => {
                try {
                    const resp = await fetch(
                        'https://www.instagram.com/api/v1/archive/reel/day_shells/'
                        + '?include_suggested_highlights=false&timezone_offset=0&initial_load=true',
                        {
                            credentials: 'include',
                            headers: {
                                'X-IG-App-ID': '936619743392459',
                                'X-ASBD-ID': '198387',
                                'X-Instagram-AJAX': '1',
                                'Accept': 'application/json, */*',
                            }
                        }
                    );
                    const text = await resp.text();
                    return {
                        status: resp.status,
                        contentType: resp.headers.get('content-type') || '',
                        redirected: resp.redirected,
                        finalUrl: resp.url,
                        body: text.substring(0, 1000),
                    };
                } catch (e) {
                    return { error: String(e) };
                }
            }"""
        )
        browser.close()

    print("=== API RESULT ===")
    print(f"Status:       {result.get('status')}")
    print(f"Content-Type: {result.get('contentType')}")
    print(f"Redirected:   {result.get('redirected')}")
    print(f"Final URL:    {result.get('finalUrl')}")
    print(f"Body (1000c): {result.get('body', '')[:600]}")
    if result.get('error'):
        print(f"Error:        {result['error']}")

    body = result.get('body', '')
    if body:
        try:
            data = json.loads(body)
            items = data.get('items') or data.get('days') or []
            print(f"\n✅ JSON parsed OK. Keys: {list(data.keys())}")
            print(f"   Items count: {len(items)}")
            if items:
                print(f"   First item: {items[0]}")
        except Exception as e:
            print(f"\n❌ JSON parse failed: {e}")
            print(f"   Body: {body[:300]}")
    else:
        print("\n❌ Empty body — Instagram blocked the request.")


if __name__ == "__main__":
    main()
