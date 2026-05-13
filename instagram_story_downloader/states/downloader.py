import reflex as rx
import asyncio
from typing import TypedDict, Optional
import logging
import instaloader
from pathlib import Path
import re


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


L = instaloader.Instaloader(quiet=True, download_video_thumbnails=False)
L.context.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


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
        if self.session_loaded:
            return
        session_dir = Path.home() / ".config" / "instaloader"
        if session_dir.exists():
            for file in session_dir.glob("session-*"):
                username = file.name.replace("session-", "")
                try:
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(
                        None, L.load_session_from_file, username, file
                    )
                    self.session_username = username
                    self.session_loaded = True
                    return
                except Exception as e:
                    logging.exception(
                        f"Failed to load session for {username}: {e}"
                    )

    @rx.event
    async def handle_submit(self, form_data: dict):
        url = form_data.get("story_url", "").strip()
        self.story_url = url
        if not url:
            self.status = "error"
            self.error_message = "Please enter a URL."
            return
        match = re.search("instagram\\.com/stories/([^/]+)/(\\d+)", url)
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
            story_item = await loop.run_in_executor(
                None,
                instaloader.StoryItem.from_mediaid,
                L.context,
                int(media_id),
            )
            is_video = story_item.is_video
            image_url = story_item.url
            video_url = story_item.video_url if is_video else None
            date_utc = story_item.date_utc
            owner_username = story_item.owner_username
            filename_base = f"{owner_username}_{date_utc.strftime('%Y%m%d_%H%M%S')}_{media_id}"
            qualities = []
            if is_video:
                qualities = [
                    {"label": "Original Quality (Video)", "url": video_url},
                    {"label": "Thumbnail (Image)", "url": image_url},
                ]
                filename = f"{filename_base}.mp4"
                primary_url = video_url
            else:
                qualities = [{"label": "Original Quality", "url": image_url}]
                filename = f"{filename_base}.jpg"
                primary_url = image_url
            self.media_items = [
                {
                    "id": media_id,
                    "type": "video" if is_video else "image",
                    "url": primary_url,
                    "thumbnail_url": image_url,
                    "filename": filename,
                    "selected": True,
                    "qualities": qualities,
                    "selected_quality_index": 0,
                }
            ]
            self.status = "ready"
        except instaloader.exceptions.QueryReturnedNotFoundException:
            logging.exception("Unexpected error")
            self.status = "error"
            self.error_message = "Story not found or has expired."
        except instaloader.exceptions.LoginRequiredException:
            logging.exception("Unexpected error")
            self.status = "error"
            self.error_message = "Login required. Please provide a valid session to view this story."
        except instaloader.exceptions.ConnectionException:
            logging.exception("Unexpected error")
            self.status = "error"
            self.error_message = (
                "Network connection error. Please try again later."
            )
        except Exception as e:
            logging.exception(f"Error fetching stories: {e}")
            self.status = "error"
            self.error_message = "Failed to fetch stories. Please ensure the profile is public or you have access."
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
            url = item["qualities"][quality_idx]["url"]
            filename = item["filename"]
            if "Thumbnail" in item["qualities"][quality_idx]["label"]:
                filename = filename.rsplit(".", 1)[0] + ".jpg"
            yield rx.download(url=url, filename=filename)

    @rx.event
    def download_single(self, item_id: str):
        for item in self.media_items:
            if item["id"] == item_id:
                quality_idx = item["selected_quality_index"]
                url = item["qualities"][quality_idx]["url"]
                filename = item["filename"]
                if "Thumbnail" in item["qualities"][quality_idx]["label"]:
                    filename = filename.rsplit(".", 1)[0] + ".jpg"
                yield rx.toast(f"Downloading {filename}...", duration=2000)
                yield rx.download(url=url, filename=filename)