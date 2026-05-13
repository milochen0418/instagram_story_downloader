import reflex as rx
import asyncio
from typing import TypedDict
import logging
import re
import urllib.parse
import datetime
import json as _json
import yt_dlp
from reflex.config import get_config


def _trigger_download_script(cdn_url: str, filename: str) -> str:
    """Build a JS snippet that downloads cdn_url via the backend proxy.

    Uses the absolute backend URL (api_url from rxconfig) so the request
    goes to port 8000 directly, bypassing the Vite dev-server at port 3000
    which only serves the SPA and cannot route /proxy-download.
    """
    backend = get_config().api_url.rstrip("/")
    params = urllib.parse.urlencode({"url": cdn_url, "filename": filename})
    full_url = f"{backend}/proxy-download?{params}"
    # Minimal JS: create an invisible anchor, click it, remove it.
    safe_url = full_url.replace("'", "%27")
    safe_fn = filename.replace("'", "\'")
    return (
        f"var _a=document.createElement('a');"
        f"_a.href='{safe_url}';"
        f"_a.download='{safe_fn}';"
        f"document.body.appendChild(_a);"
        f"_a.click();"
        f"document.body.removeChild(_a);"
    )


class QualityDict(TypedDict):
    label: str
    url: str


class MediaItem(TypedDict):
    id: str
    type: str
    url: str
    thumbnail_url: str
    filename: str
    selected: bool
    qualities: list[QualityDict]
    selected_quality_index: int


class ArchiveMonthItem(TypedDict):
    year_month: str   # "2024-01"
    label: str        # "January 2024"
    count: int
    story_urls: list[str]


# Browsers to try for cookies, in order of preference on macOS
# Chrome first: Safari requires Full Disk Access which is usually blocked
_BROWSERS_TO_TRY = ["chrome", "firefox", "safari", "edge", "chromium", "brave"]


def _best_thumbnail(thumbnails: list) -> str:
    if not thumbnails:
        return ""
    sorted_thumbs = sorted(
        thumbnails,
        key=lambda t: (t.get("width") or 0) * (t.get("height") or 0),
        reverse=True,
    )
    return sorted_thumbs[0].get("url", "")


def _check_browser_has_instagram_cookies(browser: str) -> bool:
    """Return True if the given browser has Instagram session cookies."""
    try:
        ydl_opts = {
            "cookiesfrombrowser": (browser,),
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            for cookie in ydl.cookiejar:
                domain = getattr(cookie, "domain", "")
                name = getattr(cookie, "name", "")
                if "instagram.com" in domain and name in ("sessionid", "ds_user_id"):
                    return True
    except Exception:
        pass
    return False


def _extract_with_browser(url: str, browser: str) -> dict:
    ydl_opts = {
        "cookiesfrombrowser": (browser,),
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)


def _build_media_item(entry: dict, username: str, media_id: str) -> MediaItem:
    """Convert a yt-dlp info dict entry into a MediaItem."""
    formats = entry.get("formats", [])
    thumbnail = entry.get("thumbnail", "") or _best_thumbnail(
        entry.get("thumbnails", [])
    )
    ext = entry.get("ext", "mp4")

    # Priority 1: combined mp4 formats (vcodec is Python None — not string 'none').
    # Instagram returns these as full video+audio mp4 files with signed CDN URLs.
    combined_mp4 = [
        f
        for f in formats
        if f.get("vcodec") is None
        and f.get("ext") == "mp4"
        and f.get("url")
        and f.get("protocol") == "https"
    ]
    # Deduplicate by URL (Instagram often has duplicates with different format_id)
    seen_urls: set = set()
    unique_combined: list = []
    for f in combined_mp4:
        u = f.get("url", "")
        if u not in seen_urls:
            seen_urls.add(u)
            unique_combined.append(f)

    if unique_combined:
        unique_combined.sort(key=lambda f: (f.get("height") or 0), reverse=True)
        qualities: list[QualityDict] = []
        for fmt in unique_combined[:3]:
            h = fmt.get("height")
            label = f"{h}p" if h else "Original"
            qualities.append({"label": label, "url": fmt["url"]})
        if thumbnail:
            qualities.append({"label": "Thumbnail (Image)", "url": thumbnail})
        return {
            "id": media_id,
            "type": "video",
            "url": qualities[0]["url"],
            "thumbnail_url": thumbnail,
            "filename": f"{username}_{media_id}.mp4",
            "selected": True,
            "qualities": qualities,
            "selected_quality_index": 0,
        }

    # Priority 2: DASH video formats (video codec present, audio separate).
    # These are video-only streams; we still offer them for download.
    video_formats = [
        f
        for f in formats
        if f.get("vcodec") and f.get("vcodec") != "none" and f.get("url")
    ]

    if video_formats:
        video_formats.sort(key=lambda f: (f.get("height") or 0), reverse=True)
        qualities2: list[QualityDict] = []
        seen_heights: set = set()
        for fmt in video_formats:
            h = fmt.get("height")
            if h and h in seen_heights:
                continue
            if h:
                seen_heights.add(h)
            label = f"{h}p" if h else (fmt.get("format_note") or "Video")
            qualities2.append({"label": label, "url": fmt["url"]})
            if len(qualities2) >= 4:
                break
        if thumbnail:
            qualities2.append({"label": "Thumbnail (Image)", "url": thumbnail})
        return {
            "id": media_id,
            "type": "video",
            "url": qualities2[0]["url"],
            "thumbnail_url": thumbnail,
            "filename": f"{username}_{media_id}.mp4",
            "selected": True,
            "qualities": qualities2,
            "selected_quality_index": 0,
        }

    # Priority 3: Image (no video format found)
    image_url = entry.get("url", "")
    if not image_url and formats:
        image_url = formats[-1].get("url", "") or formats[0].get("url", "")
    if not image_url:
        image_url = thumbnail
    file_ext = ext if ext not in ("mp4", "webm", "mov") else "jpg"
    return {
        "id": media_id,
        "type": "image",
        "url": image_url,
        "thumbnail_url": thumbnail or image_url,
        "filename": f"{username}_{media_id}.{file_ext}",
        "selected": True,
        "qualities": [{"label": "Original Quality", "url": image_url}],
        "selected_quality_index": 0,
    }


# ─────────────────────────────────────────────────────────────────────
# Instagram archive helpers — Playwright-based
#
# BACKGROUND:
#   Direct httpx requests to Instagram's internal API return empty body
#   (bot detection). The reliable approach:
#   1. Launch headless Chromium with the user's session cookies
#   2. Navigate to the archive page so Instagram's own JS runs
#   3. Intercept automatic API calls (for day_shells)
#   4. Make in-page fetch() calls for reels_media (works same-origin)
#
# API response facts (confirmed by live testing):
#   day_shells : Content-Type application/x-javascript
#                Body prefix "for (;;);" (XSSI protection)
#                JSON: {"payload": {"items": [
#                  {"id":"archiveDay:XXXXXXXXX", "timestamp": UNIX,
#                   "media_count": N}, ...]}}
#   reels_media: Content-Type application/json
#                Body: {"reels": {"archiveDay:XXX": {reel_obj}}}
#                Each reel_obj has "items": [{media_item}, ...]
# ─────────────────────────────────────────────────────────────────────

_IG_APP_ID = "936619743392459"
_PW_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_PW_LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled", "--no-sandbox"]


def _get_ig_session_cookies() -> tuple[dict[str, str], str]:
    """Return Instagram session cookies (plain dict) + browser name.

    Tries each browser in _BROWSERS_TO_TRY in order.
    Raises RuntimeError if no browser has an Instagram session.
    """
    for browser in _BROWSERS_TO_TRY:
        try:
            cookies: dict[str, str] = {}
            ydl_opts = {
                "cookiesfrombrowser": (browser,),
                "quiet": True,
                "no_warnings": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                for cookie in ydl.cookiejar:
                    if "instagram.com" in getattr(cookie, "domain", ""):
                        cookies[cookie.name] = cookie.value
            if "sessionid" in cookies:
                return cookies, browser
        except Exception:
            continue
    raise RuntimeError(
        "No Instagram session found. "
        "Please log in to Instagram in Chrome or Firefox first."
    )


def _pw_cookies(cookies: dict[str, str]) -> list[dict]:
    """Convert plain cookie dict to Playwright cookie format."""
    return [
        {
            "name": k,
            "value": v,
            "domain": ".instagram.com",
            "path": "/",
            "secure": True,
            "sameSite": "None",
            "httpOnly": k in ("sessionid", "ds_user_id"),
        }
        for k, v in cookies.items()
    ]


def _parse_ig_body(body: str) -> dict:
    """Parse Instagram API response body.

    Handles XSSI protection prefix "for (;;);" and payload wrapper.
    Works for both day_shells (application/x-javascript) and
    reels_media (application/json) responses.
    """
    s = body.strip()
    if s.startswith("for (;;);"):
        s = s[9:]
    data = _json.loads(s)
    return data.get("payload", data)


def _fetch_day_shells(cookies: dict[str, str]) -> list[dict]:
    """Navigate to archive page and intercept the day_shells API response.

    Instagram's page JS automatically calls day_shells on load.
    We intercept that response rather than making a direct httpx call
    (which is blocked by bot detection).

    Returns list of day-shell items:
    [{"id": "archiveDay:XXXXXXXXX", "timestamp": UNIX, "media_count": N}, ...]
    """
    from playwright.sync_api import sync_playwright as _sync_playwright

    captured_items: list[dict] = []

    def _on_response(response) -> None:
        if "day_shells" in response.url and "instagram.com" in response.url:
            try:
                body = response.body().decode("utf-8", errors="replace")
                if body:
                    data = _parse_ig_body(body)
                    items = data.get("items") or data.get("days") or []
                    captured_items.extend(items)
            except Exception as e:
                logging.warning(f"day_shells parse error: {e}")

    with _sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=_PW_LAUNCH_ARGS)
        ctx = browser.new_context(user_agent=_PW_UA)
        ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )
        ctx.add_cookies(_pw_cookies(cookies))
        page = ctx.new_page()
        page.on("response", _on_response)  # register BEFORE navigating
        page.goto(
            "https://www.instagram.com/archive/stories/",
            wait_until="networkidle",
            timeout=30000,
        )
        browser.close()

    return captured_items


def _fetch_reels_by_ids(
    cookies: dict[str, str],
    reel_ids: list[str],
) -> dict[str, dict]:
    """Open archive page and use in-page fetch to retrieve reel media.

    Must use Playwright because the reels_media endpoint only responds
    to requests originating from the Instagram page context (same-origin
    fetch with Instagram's own auth headers set by its JS).

    reel_ids: list of "archiveDay:XXXXXXXXX" strings
    Returns dict: {"archiveDay:XXX": reel_object, ...}
    """
    from playwright.sync_api import sync_playwright as _sync_playwright

    result_reels: dict[str, dict] = {}
    BATCH = 20

    with _sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=_PW_LAUNCH_ARGS)
        ctx = browser.new_context(user_agent=_PW_UA)
        ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )
        ctx.add_cookies(_pw_cookies(cookies))
        page = ctx.new_page()
        # Navigate to establish the Instagram auth context (sets x-ig-www-claim etc.)
        page.goto(
            "https://www.instagram.com/archive/stories/",
            wait_until="networkidle",
            timeout=30000,
        )
        for i in range(0, len(reel_ids), BATCH):
            batch = reel_ids[i : i + BATCH]
            ids_param = ",".join(batch)
            try:
                result = page.evaluate(
                    """async (idsParam) => {
                        try {
                            const r = await fetch(
                                '/api/v1/feed/reels_media/?reel_ids=' + encodeURIComponent(idsParam),
                                {
                                    credentials: 'include',
                                    headers: {
                                        'X-IG-App-ID': '936619743392459',
                                        'Accept': 'application/json, */*',
                                    }
                                }
                            );
                            return {status: r.status, ct: r.headers.get('content-type')||'', body: await r.text()};
                        } catch(e) { return {error: String(e)}; }
                    }""",
                    ids_param,
                )
            except Exception as e:
                logging.warning(f"reels_media evaluate error for batch {i}: {e}")
                continue
            if result.get("error"):
                logging.warning(f"reels_media JS error: {result['error']}")
                continue
            body = result.get("body", "")
            ct = result.get("ct", "")
            if not body or "html" in ct:
                logging.warning(f"reels_media unexpected response: status={result.get('status')} ct={ct!r}")
                continue
            try:
                data = _parse_ig_body(body)
                reels = data.get("reels") or {}
                result_reels.update(reels)
            except Exception as e:
                logging.warning(f"reels_media parse error: {e}")
        browser.close()

    return result_reels


def _reel_to_entries(reel: dict, reel_id: str) -> list[dict]:
    """Convert an Instagram reel object to yt-dlp-compatible entry dicts."""
    ig_user: dict = reel.get("user") or {}
    username = ig_user.get("username") or "archive"
    full_name = ig_user.get("full_name") or username

    entries: list[dict] = []
    for item in (reel.get("items") or []):
        media_type = item.get("media_type")  # 1=photo, 2=video
        thumb_cands = (item.get("image_versions2") or {}).get("candidates") or []
        thumbnail = thumb_cands[0].get("url", "") if thumb_cands else ""
        thumbnails = [
            {
                "url": c["url"],
                "width": c.get("width", 0),
                "height": c.get("height", 0),
            }
            for c in thumb_cands
        ]
        entry: dict = {
            "id": str(item.get("pk") or item.get("id") or reel_id),
            "uploader": full_name,
            "uploader_id": username,
            "thumbnail": thumbnail,
            "thumbnails": thumbnails,
        }
        if media_type == 2:  # VIDEO
            video_versions = sorted(
                item.get("video_versions") or [],
                key=lambda v: (v.get("width", 0) * v.get("height", 0)),
                reverse=True,
            )
            if video_versions:
                entry["ext"] = "mp4"
                entry["url"] = video_versions[0]["url"]
                # vcodec=None signals a combined video+audio stream to _build_media_item
                entry["formats"] = [
                    {
                        "format_id": f"v{v.get('height', 0)}p",
                        "url": v["url"],
                        "width": v.get("width"),
                        "height": v.get("height"),
                        "vcodec": None,
                        "ext": "mp4",
                        "protocol": "https",
                    }
                    for v in video_versions
                ]
        else:  # PHOTO
            if thumb_cands:
                entry["url"] = thumb_cands[0]["url"]
                entry["ext"] = "jpg"
        if entry.get("url"):
            entries.append(entry)

    return entries


class DownloaderState(rx.State):
    story_url: str = ""
    is_loading: bool = False
    status: str = "idle"
    error_message: str = ""
    media_items: list[MediaItem] = []
    session_username: str = ""
    session_loaded: bool = False
    # Archive browser state
    archive_months: list[ArchiveMonthItem] = []
    archive_status: str = "idle"  # idle | loading_months | ready_months | error_months
    archive_error: str = ""
    active_tab: str = "url"  # url | archive
    archive_loading_progress: int = 0
    archive_loading_total: int = 0
    loading_month: str = ""  # year_month of the card currently being fetched
    result_source: str = ""  # "url" | "archive"
    result_source_label: str = ""  # URL string or month label e.g. "November 2018"
    lightbox_open: bool = False
    lightbox_index: int = 0

    @rx.var
    def status_label(self) -> str:
        if self.status == "analyzing" and self.archive_loading_total > 0:
            return f"Loading {self.archive_loading_progress}/{self.archive_loading_total}..."
        return {
            "idle": "Ready",
            "analyzing": "Analyzing...",
            "ready": "Ready to Download",
            "error": "Error",
        }.get(self.status, "Ready")

    @rx.var
    def status_color(self) -> str:
        return {
            "idle": "bg-gray-100 text-gray-600",
            "analyzing": "bg-amber-100 text-amber-600 animate-pulse",
            "ready": "bg-green-100 text-green-600",
            "error": "bg-red-100 text-red-600",
        }.get(self.status, "bg-gray-100 text-gray-600")

    @rx.var
    def video_count(self) -> int:
        return len(
            [item for item in self.media_items if item["type"] == "video"]
        )

    @rx.var
    def image_count(self) -> int:
        return len(
            [item for item in self.media_items if item["type"] == "image"]
        )

    @rx.var
    def selected_count(self) -> int:
        return len([item for item in self.media_items if item["selected"]])

    @rx.var
    def lightbox_item(self) -> MediaItem:
        if not self.media_items:
            return {
                "id": "", "type": "image", "url": "", "thumbnail_url": "",
                "filename": "", "selected": False, "qualities": [], "selected_quality_index": 0,
            }
        idx = max(0, min(self.lightbox_index, len(self.media_items) - 1))
        return self.media_items[idx]

    @rx.var
    def lightbox_counter(self) -> str:
        if not self.media_items:
            return ""
        return f"{self.lightbox_index + 1} / {len(self.media_items)}"

    @rx.var
    def lightbox_has_prev(self) -> bool:
        return self.lightbox_index > 0

    @rx.var
    def lightbox_has_next(self) -> bool:
        return self.lightbox_index < len(self.media_items) - 1

    @rx.event
    async def load_session(self):
        """Detect if any browser has Instagram session cookies (via yt-dlp)."""
        if self.session_loaded:
            return
        loop = asyncio.get_running_loop()
        for browser in _BROWSERS_TO_TRY:
            try:
                found = await loop.run_in_executor(
                    None, _check_browser_has_instagram_cookies, browser
                )
                if found:
                    self.session_loaded = True
                    self.session_username = browser
                    return
            except Exception:
                continue

    @rx.event
    async def handle_submit(self, form_data: dict):
        url = form_data.get("story_url", "").strip()
        self.story_url = url
        if not url:
            self.status = "error"
            self.error_message = "Please enter a URL."
            return

        # User may paste the archive-listing page URL — redirect to Browse Archive tab
        if re.search(r"instagram\.com/archive/stories/?$", url):
            self.active_tab = "archive"
            self.status = "idle"
            self.error_message = ""
            return

        match = re.search(r"instagram\.com/stories/([^/]+)/(\d+)", url)
        if not match:
            self.status = "error"
            self.error_message = (
                "Invalid URL. Must be an Instagram Story or Archive link "
                "(e.g., instagram.com/stories/username/id/ or "
                "instagram.com/stories/archive/id/)."
            )
            return

        username = match.group(1)
        media_id = match.group(2)
        is_archive = username == "archive"

        self.is_loading = True
        self.status = "analyzing"
        self.error_message = ""
        self.media_items = []
        yield

        try:
            loop = asyncio.get_running_loop()
            media_items: list[MediaItem] = []
            used_browser = "none"

            if is_archive:
                # Archived stories require Playwright (httpx blocked by bot detection).
                # media_id from URL regex is the numeric part; try archiveDay: prefix.
                def _extract_archive_via_playwright() -> tuple[list[MediaItem], str]:
                    cookies, browser = _get_ig_session_cookies()
                    # Try both reel_id forms: "archiveDay:NNNN" and plain "NNNN"
                    reel_id_candidates = [
                        f"archiveDay:{media_id}",
                        media_id,
                    ]
                    for reel_id_try in reel_id_candidates:
                        reels = _fetch_reels_by_ids(cookies, [reel_id_try])
                        if reels:
                            items: list[MediaItem] = []
                            for rid, reel in reels.items():
                                for i, entry in enumerate(_reel_to_entries(reel, rid)):
                                    item_id = entry.get("id") or f"{media_id}_{i}"
                                    uname = (
                                        entry.get("uploader_id")
                                        or entry.get("uploader")
                                        or "archive"
                                    )
                                    items.append(_build_media_item(entry, uname, item_id))
                            if items:
                                return items, browser
                    raise RuntimeError("Archived reel not found.")

                media_items, used_browser = await loop.run_in_executor(
                    None, _extract_archive_via_playwright
                )

            if not media_items:
                # Regular story URL (or archive API fallback): use yt-dlp with browser cookies
                def extract_info() -> tuple[dict, str]:
                    last_error: Exception | None = None
                    for browser in _BROWSERS_TO_TRY:
                        try:
                            info = _extract_with_browser(url, browser)
                            if info:
                                return info, browser
                        except Exception as e:
                            last_error = e
                            continue
                    # Last resort: try without cookies
                    try:
                        ydl_opts = {"quiet": True, "no_warnings": True}
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(url, download=False)
                            if info:
                                return info, "none"
                    except Exception as e:
                        last_error = e
                    raise last_error or Exception(
                        "Failed to extract story info from all browsers"
                    )

                info, used_browser = await loop.run_in_executor(None, extract_info)

                entries: list[dict] = []
                if info.get("_type") == "playlist":
                    entries = [e for e in (info.get("entries") or []) if e]
                else:
                    entries = [info]

                for i, entry in enumerate(entries):
                    item_id = entry.get("id") or f"{media_id}_{i}"
                    actual_uname = (
                        entry.get("uploader_id") or entry.get("uploader") or username
                    )
                    media_items.append(_build_media_item(entry, actual_uname, item_id))

            if media_items:
                self.media_items = media_items
                self.status = "ready"
                self.result_source = "url"
                self.result_source_label = url
                if used_browser != "none":
                    self.session_loaded = True
                    self.session_username = used_browser
            else:
                self.status = "error"
                self.error_message = "No media found in this story."

        except Exception as e:
            logging.exception(f"Error fetching story: {e}")
            err_lower = str(e).lower()
            if any(
                k in err_lower
                for k in ("login", "private", "authenticate", "password", "session")
            ):
                self.status = "error"
                self.error_message = (
                    "Login required. Please log in to Instagram in your browser "
                    "first, then try again."
                )
            elif any(
                k in err_lower for k in ("not found", "404", "does not exist")
            ):
                self.status = "error"
                self.error_message = "Story not found or has expired."
            else:
                self.status = "error"
                self.error_message = f"Failed to fetch story: {e}"
        finally:
            self.is_loading = False

    @rx.event
    def toggle_item_selection(self, item_id: str):
        for item in self.media_items:
            if item["id"] == item_id:
                item["selected"] = not item["selected"]
        self.media_items = list(self.media_items)

    @rx.event
    def select_all(self):
        for item in self.media_items:
            item["selected"] = True
        self.media_items = list(self.media_items)

    @rx.event
    def deselect_all(self):
        for item in self.media_items:
            item["selected"] = False
        self.media_items = list(self.media_items)

    @rx.event
    def change_quality(self, item_id: str, quality_index: str):
        q_idx = int(quality_index)
        for item in self.media_items:
            if item["id"] == item_id:
                item["selected_quality_index"] = q_idx
        self.media_items = list(self.media_items)

    @rx.event
    def download_selected(self):
        selected = [item for item in self.media_items if item["selected"]]
        if not selected:
            return rx.toast("No items selected for download.", duration=3000)
        yield rx.toast(
            f"Starting download for {len(selected)} items...", duration=3000
        )
        for item in selected:
            quality_idx = item["selected_quality_index"]
            cdn_url = item["qualities"][quality_idx]["url"]
            filename = item["filename"]
            if "Thumbnail" in item["qualities"][quality_idx]["label"]:
                filename = filename.rsplit(".", 1)[0] + ".jpg"
            yield rx.call_script(_trigger_download_script(cdn_url, filename))

    @rx.event
    def download_single(self, item_id: str):
        for item in self.media_items:
            if item["id"] == item_id:
                quality_idx = item["selected_quality_index"]
                cdn_url = item["qualities"][quality_idx]["url"]
                filename = item["filename"]
                if "Thumbnail" in item["qualities"][quality_idx]["label"]:
                    filename = filename.rsplit(".", 1)[0] + ".jpg"
                yield rx.toast(f"Downloading {filename}...", duration=2000)
                yield rx.call_script(_trigger_download_script(cdn_url, filename))

    # ──────────────────────────────────────────────
    # Archive browser events
    # ──────────────────────────────────────────────

    # ── Lightbox / media-preview events ─────────────────────────────

    @rx.event
    async def open_lightbox_for_item(self, item_id: str):
        for i, m in enumerate(self.media_items):
            if m["id"] == item_id:
                self.lightbox_open = True
                self.lightbox_index = i
                yield rx.call_script(
                    "setTimeout(function(){var el=document.getElementById('lightbox-wrapper');if(el)el.focus();},80)"
                )
                return

    @rx.event
    def close_lightbox(self):
        self.lightbox_open = False

    @rx.event
    async def lightbox_prev(self):
        if self.lightbox_index > 0:
            self.lightbox_index -= 1
            yield rx.call_script(
                "var v=document.getElementById('lightbox-video');if(v){v.load();v.play().catch(function(){});}"
            )

    @rx.event
    async def lightbox_next(self):
        if self.lightbox_index < len(self.media_items) - 1:
            self.lightbox_index += 1
            yield rx.call_script(
                "var v=document.getElementById('lightbox-video');if(v){v.load();v.play().catch(function(){});}"
            )

    @rx.event
    def lightbox_key_nav(self, key: str):
        if key == "ArrowLeft" and self.lightbox_index > 0:
            self.lightbox_index -= 1
        elif key == "ArrowRight" and self.lightbox_index < len(self.media_items) - 1:
            self.lightbox_index += 1
        elif key == "Escape":
            self.lightbox_open = False

    @rx.event
    def setup_client_scripts(self):
        yield rx.call_script(
            """if(!window.__vcHover){
  window.__vcHover=true;
  document.addEventListener('mouseover',function(e){
    var c=e.target&&e.target.closest&&e.target.closest('.vc-thumb');
    if(!c)return;
    var v=c.querySelector('video');
    if(!v)return;
    if(!v.src||v.src===window.location.href)v.src=v.dataset.src||'';
    v.play().catch(function(){});
    v.style.opacity='1';
    var pi=c.querySelector('.play-icon-overlay');
    if(pi)pi.style.opacity='0';
  });
  document.addEventListener('mouseout',function(e){
    var c=e.target&&e.target.closest&&e.target.closest('.vc-thumb');
    if(!c)return;
    if(c.contains(e.relatedTarget))return;
    var v=c.querySelector('video');
    if(!v)return;
    v.pause();
    v.style.opacity='0';
    var pi=c.querySelector('.play-icon-overlay');
    if(pi)pi.style.opacity='1';
  });
  document.addEventListener('keydown',function(e){
    var w=document.getElementById('lightbox-wrapper');
    if(!w)return;
    if(e.key==='ArrowLeft'){var b=w.querySelector('[title="Previous (\\u2190)"]');if(b&&!b.disabled)b.click();}
    else if(e.key==='ArrowRight'){var b=w.querySelector('[title="Next (\\u2192)"]');if(b&&!b.disabled)b.click();}
    else if(e.key==='Escape'){var b=w.querySelector('[title="Close (Esc)"]');if(b)b.click();}
  });
}"""
        )

    # ── Archive browser events ────────────────────────────────────────

    @rx.event
    def switch_to_url_tab(self):
        self.active_tab = "url"

    @rx.event
    def switch_to_archive_tab(self):
        self.active_tab = "archive"

    @rx.event
    async def load_archive_months(self):
        """Fetch archive day-shell list via Playwright and group by month.

        Navigates to instagram.com/archive/stories/ in a headless browser,
        intercepts the automatic day_shells API response, then groups the
        returned day objects into months for the month-browser UI.

        story_urls stores "archiveDay:XXXXXXXXX" IDs (the reel IDs used by
        the reels_media endpoint — no separate day_reels lookup needed).
        """
        self.archive_status = "loading_months"
        self.archive_error = ""
        self.archive_months = []
        yield
        try:
            loop = asyncio.get_running_loop()

            def fetch_months() -> tuple[list[ArchiveMonthItem], str]:
                cookies, browser = _get_ig_session_cookies()
                day_shells = _fetch_day_shells(cookies)
                if not day_shells:
                    raise RuntimeError(
                        "No archived stories found. "
                        "Make sure you have archived stories and are logged in "
                        "to Instagram in Chrome or Firefox."
                    )
                # Group by year-month using the timestamp field.
                # Each shell: {"id": "archiveDay:XXXXXXXXX", "timestamp": UNIX, "media_count": N}
                # The "id" (archiveDay:XXX) is directly passed to reels_media — no extra step.
                month_map: dict[str, dict] = {}
                for shell in day_shells:
                    day_id = str(shell.get("id") or "")
                    ts = shell.get("timestamp") or 0
                    media_count = int(shell.get("media_count") or 1)
                    if not ts:
                        continue
                    dt = datetime.datetime.fromtimestamp(ts)
                    ym = f"{dt.year:04d}-{dt.month:02d}"
                    if ym not in month_map:
                        month_map[ym] = {"count": 0, "day_ids": []}
                    month_map[ym]["count"] += media_count
                    if day_id:
                        month_map[ym]["day_ids"].append(day_id)

                months: list[ArchiveMonthItem] = []
                for ym in sorted(month_map.keys(), reverse=True):
                    try:
                        dt2 = datetime.datetime.strptime(ym, "%Y-%m")
                        label = dt2.strftime("%B %Y")
                    except Exception:
                        label = ym
                    months.append(
                        {
                            "year_month": ym,
                            "label": label,
                            "count": month_map[ym]["count"],
                            "story_urls": month_map[ym]["day_ids"],
                        }
                    )
                return months, browser

            months, used_browser = await loop.run_in_executor(None, fetch_months)
            self.archive_months = months
            self.archive_status = "ready_months"
            self.session_loaded = True
            self.session_username = used_browser

        except Exception as e:
            logging.exception(f"Error loading archive: {e}")
            self.archive_status = "error_months"
            self.archive_error = str(e)

    @rx.event
    async def select_archive_month(self, year_month: str):
        """Load all story media for the given month via Playwright.

        The archiveDay:XXX IDs stored in story_urls are the reel IDs for
        reels_media — no separate day_reels step needed.
        All fetches happen in a single Playwright session for efficiency.
        """
        day_ids: list[str] = []
        for m in self.archive_months:
            if m["year_month"] == year_month:
                day_ids = list(m["story_urls"])
                break
        if not day_ids:
            return

        self.is_loading = True
        self.loading_month = year_month
        self.status = "analyzing"
        self.error_message = ""
        self.media_items = []
        self.archive_loading_progress = 0
        self.archive_loading_total = len(day_ids)
        yield

        loop = asyncio.get_running_loop()

        try:
            cookies, used_browser = await loop.run_in_executor(
                None, _get_ig_session_cookies
            )
        except Exception as e:
            self.status = "error"
            self.error_message = f"Instagram session not found: {e}"
            self.is_loading = False
            return

        # Fetch all reels for the selected month in ONE Playwright session
        def fetch_month_reels() -> dict[str, dict]:
            return _fetch_reels_by_ids(cookies, day_ids)

        try:
            reels = await loop.run_in_executor(None, fetch_month_reels)
        except Exception as e:
            logging.exception(f"Error loading month reels: {e}")
            self.status = "error"
            self.error_message = f"Failed to load archive media: {e}"
            self.is_loading = False
            return

        all_media: list[MediaItem] = []
        for reel_id, reel in reels.items():
            try:
                for i, entry in enumerate(_reel_to_entries(reel, reel_id)):
                    item_id = entry.get("id") or f"arch_{reel_id}_{i}"
                    uname = (
                        entry.get("uploader_id")
                        or entry.get("uploader")
                        or "archive"
                    )
                    all_media.append(_build_media_item(entry, uname, item_id))
            except Exception:
                pass

        if all_media:
            self.media_items = all_media
            self.status = "ready"
            self.session_loaded = True
            self.session_username = used_browser
            # Set source label for the results header
            for m in self.archive_months:
                if m["year_month"] == year_month:
                    self.result_source = "archive"
                    self.result_source_label = m["label"]
                    break
        else:
            self.status = "error"
            self.error_message = "No media found for the selected month."

        self.archive_loading_progress = len(day_ids)
        self.archive_loading_total = 0
        self.loading_month = ""
        self.is_loading = False
        # Scroll results into view after content is ready
        yield rx.call_script(
            "setTimeout(()=>{var el=document.getElementById('media-results');if(el)el.scrollIntoView({behavior:'smooth',block:'start'});},100)"
        )