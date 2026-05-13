import reflex as rx
import asyncio
from typing import TypedDict
import logging
import re
import urllib.parse
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


class DownloaderState(rx.State):
    story_url: str = ""
    is_loading: bool = False
    status: str = "idle"
    error_message: str = ""
    media_items: list[MediaItem] = []
    session_username: str = ""
    session_loaded: bool = False

    @rx.var
    def status_label(self) -> str:
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
        match = re.search(r"instagram\.com/stories/([^/]+)/(\d+)", url)
        if not match:
            self.status = "error"
            self.error_message = "Invalid URL. Must be an Instagram Story link (e.g., instagram.com/stories/username/id/)."
            return
        username = match.group(1)
        media_id = match.group(2)
        self.is_loading = True
        self.status = "analyzing"
        self.error_message = ""
        self.media_items = []
        yield
        try:
            loop = asyncio.get_running_loop()

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

            # Normalise: handle both single-entry and playlist results
            entries: list[dict] = []
            if info.get("_type") == "playlist":
                entries = [e for e in (info.get("entries") or []) if e]
            else:
                entries = [info]

            media_items: list[MediaItem] = []
            for i, entry in enumerate(entries):
                item_id = entry.get("id") or f"{media_id}_{i}"
                media_items.append(_build_media_item(entry, username, item_id))

            if media_items:
                self.media_items = media_items
                self.status = "ready"
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
                for k in ("login", "private", "authenticate", "password")
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