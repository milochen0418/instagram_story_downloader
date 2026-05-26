import urllib.parse
import httpx
import reflex as rx
from starlette.requests import Request
from starlette.responses import StreamingResponse, JSONResponse
from instagram_story_downloader.states.downloader import (
    DownloaderState,
    ArchiveMonthItem,
    ProfileCategoryItem,
)
from instagram_story_downloader.components.media_card import media_card

# Allowlist of CDN host suffixes that we're willing to proxy.
_ALLOWED_CDN_HOSTS = (
    ".fbcdn.net",
    ".cdninstagram.com",
    "instagram.com",
)


async def proxy_download(request: Request):
    """Stream an Instagram CDN URL back to the browser as a file download."""
    url = request.query_params.get("url", "")
    filename = request.query_params.get("filename", "download")
    parsed = urllib.parse.urlparse(url)
    if not url or not any(parsed.netloc.endswith(h) for h in _ALLOWED_CDN_HOSTS):
        return JSONResponse({"error": "URL not allowed"}, status_code=400)

    safe_filename = urllib.parse.quote(filename)
    client = httpx.AsyncClient(follow_redirects=True, timeout=60)
    upstream = await client.send(
        client.build_request("GET", url), stream=True
    )
    content_type = upstream.headers.get("content-type", "application/octet-stream")
    headers = {
        "Content-Disposition": f'attachment; filename="{safe_filename}"',
    }
    cl = upstream.headers.get("content-length")
    if cl:
        headers["Content-Length"] = cl

    async def _stream():
        try:
            async for chunk in upstream.aiter_bytes(65536):
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(_stream(), media_type=content_type, headers=headers)


def lightbox_modal() -> rx.Component:
    """Floating draggable/resizable player window — page stays fully interactive."""
    return rx.cond(
        DownloaderState.lightbox_open,
        rx.el.div(
            # ── Title bar (drag handle) ──────────────────────────
            rx.el.div(
                rx.icon("grip-horizontal", class_name="h-4 w-4 text-white/30 shrink-0"),
                rx.el.span(
                    DownloaderState.lightbox_counter,
                    class_name="text-white/50 text-xs font-medium tabular-nums shrink-0 ml-2",
                ),
                rx.el.span(
                    DownloaderState.lightbox_item["filename"],
                    class_name="text-white/70 text-xs truncate flex-1 mx-3",
                ),
                rx.el.button(
                    rx.icon("x", class_name="h-4 w-4"),
                    on_click=DownloaderState.close_lightbox,
                    class_name="shrink-0 text-white/60 hover:text-white p-1 rounded hover:bg-white/15 transition-colors",
                    title="Close (Esc)",
                ),
                class_name="float-player-titlebar flex items-center px-3 h-10 shrink-0 cursor-move select-none",
                style={
                    "background": "rgba(40,40,40,0.97)",
                    "borderRadius": "10px 10px 0 0",
                    "borderBottom": "1px solid rgba(255,255,255,0.08)",
                },
            ),
            # ── Media area ───────────────────────────────────────
            rx.el.div(
                rx.cond(
                    DownloaderState.lightbox_item["type"] == "video",
                    rx.el.video(
                        src=DownloaderState.lightbox_item["url"],
                        controls=True,
                        autoplay=True,
                        loop=False,
                        style={
                            "width": "100%",
                            "height": "100%",
                            "display": "block",
                            "objectFit": "contain",
                            "background": "#000",
                        },
                        id="lightbox-video",
                    ),
                    rx.el.img(
                        src=DownloaderState.lightbox_item["url"],
                        style={
                            "width": "100%",
                            "height": "100%",
                            "objectFit": "contain",
                        },
                    ),
                ),
                style={
                    "flex": "1",
                    "minHeight": "0",
                    "overflow": "hidden",
                    "background": "#000",
                },
            ),
            # ── Bottom nav: prev / next ──────────────────────────
            rx.el.div(
                rx.el.button(
                    rx.icon("chevron-left", class_name="h-5 w-5"),
                    on_click=DownloaderState.lightbox_prev,
                    disabled=~DownloaderState.lightbox_has_prev,
                    class_name="text-white/70 hover:text-white px-4 py-2 rounded hover:bg-white/10 transition-colors disabled:opacity-25 disabled:cursor-not-allowed",
                    title="Previous (←)",
                ),
                rx.el.span(
                    DownloaderState.lightbox_date_label,
                    class_name="text-white/50 text-xs font-medium tabular-nums",
                ),
                rx.el.button(
                    rx.icon("chevron-right", class_name="h-5 w-5"),
                    on_click=DownloaderState.lightbox_next,
                    disabled=~DownloaderState.lightbox_has_next,
                    class_name="text-white/70 hover:text-white px-4 py-2 rounded hover:bg-white/10 transition-colors disabled:opacity-25 disabled:cursor-not-allowed",
                    title="Next (→)",
                ),
                class_name="flex items-center justify-between px-2 py-1 shrink-0",
                style={
                    "background": "rgba(30,30,30,0.97)",
                    "borderTop": "1px solid rgba(255,255,255,0.06)",
                    "borderRadius": "0 0 10px 10px",
                },
            ),
            id="float-player-window",
            style={
                "position": "fixed",
                "top": "80px",
                "right": "40px",
                "width": "400px",
                "height": "520px",
                "minWidth": "260px",
                "minHeight": "200px",
                "resize": "both",
                "overflow": "hidden",
                "display": "flex",
                "flexDirection": "column",
                "borderRadius": "10px",
                "boxShadow": "0 12px 48px rgba(0,0,0,0.7), 0 0 0 1px rgba(255,255,255,0.08)",
                "zIndex": "9999",
            },
        ),
        rx.fragment(),
    )


def profile_category_card(cat: ProfileCategoryItem) -> rx.Component:
    """A clickable card for a profile category (current stories or a highlight)."""
    is_loading = DownloaderState.loading_profile_category == cat["id"]
    has_cover = cat["cover_url"] != ""
    return rx.el.button(
        rx.cond(
            is_loading,
            rx.el.div(
                rx.el.div(
                    class_name="animate-spin h-5 w-5 border-2 border-indigo-600 border-t-transparent rounded-full",
                ),
                rx.el.span("Loading...", class_name="text-xs text-indigo-600 font-semibold mt-1"),
                class_name="absolute inset-0 flex flex-col items-center justify-center bg-white/90 rounded-xl z-10",
            ),
            rx.fragment(
                # Cover image (if available) or a type-appropriate icon
                rx.cond(
                    has_cover,
                    rx.el.img(
                        src=cat["cover_url"],
                        class_name="w-14 h-14 rounded-full object-cover mb-2 border-2 border-indigo-200",
                        style={"objectFit": "cover", "objectPosition": "center", "width": "56px", "height": "56px"},
                    ),
                    rx.cond(
                        cat["category_type"] == "stories",
                        rx.icon("play-circle", class_name="h-8 w-8 text-pink-500 mb-2"),
                        rx.icon("star", class_name="h-8 w-8 text-indigo-500 mb-2"),
                    ),
                ),
                rx.el.p(
                    cat["label"],
                    class_name="font-semibold text-gray-800 text-sm text-center leading-snug",
                    style={"display": "-webkit-box", "-webkit-line-clamp": "2", "-webkit-box-orient": "vertical", "overflow": "hidden"},
                ),
                rx.cond(
                    cat["count"] > 0,
                    rx.el.p(
                        rx.el.span(cat["count"]),
                        rx.el.span(" items"),
                        class_name="text-xs text-indigo-600 font-medium mt-0.5",
                    ),
                    rx.fragment(),
                ),
            ),
        ),
        on_click=lambda: DownloaderState.select_profile_category(cat["id"]),
        disabled=DownloaderState.loading_profile_category != "",
        class_name=rx.cond(
            is_loading,
            "relative flex flex-col items-center py-4 px-3 bg-white border-2 border-indigo-400 rounded-xl shadow-md transition-all duration-200 cursor-wait w-full min-h-[120px]",
            "relative flex flex-col items-center py-4 px-3 bg-white border border-gray-200 rounded-xl hover:border-indigo-400 hover:shadow-md transition-all duration-200 cursor-pointer w-full min-h-[120px]",
        ),
    )


def profile_browser_section() -> rx.Component:
    """Category panel shown in the URL tab when a profile URL has been submitted."""
    return rx.el.div(
        # Loading spinner
        rx.cond(
            DownloaderState.profile_status == "loading",
            rx.el.div(
                rx.el.div(
                    class_name="animate-spin h-8 w-8 border-4 border-indigo-600 border-t-transparent rounded-full mb-3 mx-auto"
                ),
                rx.el.p(
                    "Loading @" + DownloaderState.profile_username + "...",
                    class_name="text-gray-500 text-center text-sm",
                ),
                class_name="py-10",
            ),
        ),
        # Error
        rx.cond(
            DownloaderState.profile_status == "error",
            rx.el.div(
                rx.icon("circle-alert", class_name="h-5 w-5 shrink-0 text-red-600"),
                rx.el.p(DownloaderState.profile_error, class_name="text-sm"),
                class_name="flex items-center gap-3 p-4 bg-red-50 text-red-700 rounded-xl border border-red-100",
            ),
        ),
        # Categories grid
        rx.cond(
            DownloaderState.profile_status == "ready",
            rx.el.div(
                rx.el.p(
                    "@" + DownloaderState.profile_username + " — click a category to load its stories",
                    class_name="text-gray-500 text-sm text-center mb-5",
                ),
                rx.el.div(
                    rx.foreach(DownloaderState.profile_categories, profile_category_card),
                    class_name="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3",
                ),
            ),
        ),
        class_name="mt-6",
    )


def archive_month_card(month: ArchiveMonthItem) -> rx.Component:
    """A clickable card for one calendar month of archived stories."""
    is_loading = DownloaderState.loading_month == month["year_month"]
    return rx.el.button(
        # Spinner overlay shown while this specific month is loading
        rx.cond(
            is_loading,
            rx.el.div(
                rx.el.div(
                    class_name="animate-spin h-5 w-5 border-2 border-indigo-600 border-t-transparent rounded-full",
                ),
                rx.el.span("Loading...", class_name="text-xs text-indigo-600 font-semibold mt-1"),
                class_name="absolute inset-0 flex flex-col items-center justify-center bg-white/90 rounded-xl z-10",
            ),
            rx.fragment(
                rx.icon("calendar", class_name="h-6 w-6 text-indigo-500 mb-2"),
                rx.el.p(month["label"], class_name="font-semibold text-gray-800 text-sm"),
                rx.el.p(
                    rx.el.span(month["count"]),
                    rx.el.span(" reels"),
                    class_name="text-xs text-indigo-600 font-medium mt-0.5",
                ),
            ),
        ),
        on_click=lambda: DownloaderState.select_archive_month(month["year_month"]),
        disabled=DownloaderState.loading_month != "",
        class_name=rx.cond(
            is_loading,
            "relative flex flex-col items-center py-4 px-3 bg-white border-2 border-indigo-400 rounded-xl shadow-md transition-all duration-200 cursor-wait w-full",
            "relative flex flex-col items-center py-4 px-3 bg-white border border-gray-200 rounded-xl hover:border-indigo-400 hover:shadow-md transition-all duration-200 cursor-pointer w-full",
        ),
    )


def archive_browser_section() -> rx.Component:
    """The archive-browser panel shown when the 'Browse Archive' tab is active."""
    return rx.el.div(
        # Idle: show load button
        rx.cond(
            DownloaderState.archive_status == "idle",
            rx.el.div(
                rx.el.p(
                    "Browse your archived stories month by month. Make sure you're logged in to Instagram in Chrome or Firefox first.",
                    class_name="text-gray-500 text-sm mb-6 text-center",
                ),
                rx.el.button(
                    rx.icon("archive", class_name="h-5 w-5"),
                    "Load My Archive",
                    on_click=DownloaderState.load_archive_months,
                    class_name="px-8 py-3 bg-indigo-600 text-white rounded-xl font-semibold hover:bg-indigo-700 transition-colors flex items-center gap-2 mx-auto shadow-md shadow-indigo-100",
                ),
                class_name="flex flex-col items-center py-12",
            ),
        ),
        # Loading months spinner
        rx.cond(
            DownloaderState.archive_status == "loading_months",
            rx.el.div(
                rx.el.div(
                    class_name="animate-spin h-10 w-10 border-4 border-indigo-600 border-t-transparent rounded-full mb-4 mx-auto"
                ),
                rx.el.p(
                    "Loading your archive list...",
                    class_name="text-gray-500 text-center",
                ),
                class_name="py-16",
            ),
        ),
        # Error
        rx.cond(
            DownloaderState.archive_status == "error_months",
            rx.el.div(
                rx.el.div(
                    rx.icon("circle-alert", class_name="h-5 w-5 shrink-0"),
                    rx.el.p(DownloaderState.archive_error),
                    class_name="flex items-center gap-3 p-4 bg-red-50 text-red-700 rounded-xl border border-red-100 mb-4",
                ),
                rx.el.button(
                    "Try Again",
                    on_click=DownloaderState.load_archive_months,
                    class_name="px-6 py-2 bg-indigo-600 text-white rounded-lg font-semibold hover:bg-indigo-700 transition-colors mx-auto block",
                ),
            ),
        ),
        # Month grid
        rx.cond(
            DownloaderState.archive_status == "ready_months",
            rx.el.div(
                rx.el.p(
                    f"Found {DownloaderState.archive_months.length()} months — click a month to load its stories",
                    class_name="text-gray-500 text-sm text-center mb-5",
                ),
                rx.el.div(
                    rx.foreach(DownloaderState.archive_months, archive_month_card),
                    class_name="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3",
                ),
            ),
        ),
    )


def index() -> rx.Component:
    return rx.el.main(
        rx.el.div(
            rx.el.header(
                rx.el.div(
                    rx.el.div(
                        rx.icon(
                            "camera", class_name="h-8 w-8 text-pink-500"
                        ),
                        rx.el.h1(
                            "MiStories",
                            class_name="text-2xl font-bold text-gray-900",
                        ),
                        class_name="flex items-center gap-3",
                    ),
                    rx.el.div(
                        DownloaderState.status_label,
                        class_name=f"px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider {DownloaderState.status_color}",
                    ),
                    class_name="flex flex-col md:flex-row items-center justify-between gap-4 w-full",
                ),
                class_name="mb-12 border-b border-gray-100 pb-8",
            ),
            rx.el.section(
                rx.el.div(
                    rx.el.div(
                        rx.cond(
                            DownloaderState.session_loaded,
                            rx.el.div(
                                rx.el.div(
                                    class_name="h-2 w-2 rounded-full bg-green-500"
                                ),
                                rx.el.span(
                                    f"Session detected via {DownloaderState.session_username} cookies",
                                    class_name="text-sm font-medium text-green-700",
                                ),
                                class_name="flex items-center gap-2 bg-green-50 px-4 py-2 rounded-full border border-green-100",
                            ),
                            rx.el.div(
                                rx.el.div(
                                    class_name="h-2 w-2 rounded-full bg-amber-500"
                                ),
                                rx.el.span(
                                    "No browser session detected — log in to Instagram in Chrome/Firefox first",
                                    class_name="text-sm font-medium text-amber-700",
                                ),
                                title="Log in to Instagram in Chrome or Firefox, then refresh this page",
                                class_name="flex items-center gap-2 bg-amber-50 px-4 py-2 rounded-full border border-amber-100 cursor-help",
                            ),
                        ),
                        class_name="mb-6 flex justify-center",
                    ),
                    # Tab buttons
                    rx.el.div(
                        rx.el.button(
                            rx.icon("link", class_name="h-4 w-4"),
                            "Single Story URL",
                            on_click=DownloaderState.switch_to_url_tab,
                            class_name=rx.cond(
                                DownloaderState.active_tab == "url",
                                "flex items-center gap-2 px-5 py-2.5 rounded-xl font-semibold text-sm bg-indigo-600 text-white shadow-sm",
                                "flex items-center gap-2 px-5 py-2.5 rounded-xl font-semibold text-sm text-gray-500 hover:text-gray-800 hover:bg-gray-100 transition-colors",
                            ),
                        ),
                        rx.el.button(
                            rx.icon("archive", class_name="h-4 w-4"),
                            "Browse Archive",
                            on_click=DownloaderState.switch_to_archive_tab,
                            class_name=rx.cond(
                                DownloaderState.active_tab == "archive",
                                "flex items-center gap-2 px-5 py-2.5 rounded-xl font-semibold text-sm bg-indigo-600 text-white shadow-sm",
                                "flex items-center gap-2 px-5 py-2.5 rounded-xl font-semibold text-sm text-gray-500 hover:text-gray-800 hover:bg-gray-100 transition-colors",
                            ),
                        ),
                        class_name="flex gap-2 mb-6 border-b border-gray-100 pb-4",
                    ),
                    # Conditional tab content
                    rx.cond(
                        DownloaderState.active_tab == "url",
                        rx.el.div(
                            rx.el.form(
                                rx.el.div(
                                    rx.el.div(
                                        rx.icon(
                                            "link",
                                            class_name="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400",
                                        ),
                                        rx.el.input(
                                            name="story_url",
                                            placeholder="Paste Instagram Story, Highlight, or Profile URL...",
                                            class_name="w-full pl-12 pr-4 py-4 rounded-xl border border-gray-200 focus:ring-4 focus:ring-indigo-100 focus:border-indigo-600 transition-all outline-none text-lg text-gray-800",
                                        ),
                                        class_name="relative flex-1",
                                    ),
                                    rx.el.button(
                                        rx.cond(
                                            DownloaderState.is_loading,
                                            rx.el.div(
                                                class_name="animate-spin h-5 w-5 border-2 border-white border-t-transparent rounded-full"
                                            ),
                                            "Analyze",
                                        ),
                                        type="submit",
                                        disabled=DownloaderState.is_loading,
                                        class_name="px-8 py-4 bg-indigo-600 text-white rounded-xl font-semibold hover:bg-indigo-700 transition-colors disabled:opacity-70 disabled:cursor-not-allowed whitespace-nowrap shadow-lg shadow-indigo-100",
                                    ),
                                    class_name="flex flex-col sm:flex-row gap-4",
                                ),
                                on_submit=DownloaderState.handle_submit,
                            ),
                            # Profile categories (shown when a profile URL was submitted)
                            rx.cond(
                                DownloaderState.profile_status != "idle",
                                profile_browser_section(),
                                rx.fragment(),
                            ),
                        ),
                        archive_browser_section(),
                    ),
                    class_name="max-w-3xl mx-auto",
                ),
                class_name="mb-8",
            ),
            rx.cond(
                DownloaderState.status == "error",
                rx.el.div(
                    rx.icon("circle_alert", class_name="h-5 w-5"),
                    rx.el.p(DownloaderState.error_message),
                    class_name="max-w-3xl mx-auto mb-8 p-4 bg-red-50 text-red-700 rounded-xl flex items-center gap-3 border border-red-100 animate-in fade-in slide-in-from-top-2",
                ),
                None,
            ),
            # Loading indicator (URL analysis or archive month loading)
            rx.cond(
                DownloaderState.is_loading,
                rx.el.div(
                    rx.el.div(
                        rx.el.div(
                            class_name="animate-spin h-10 w-10 border-4 border-indigo-600 border-t-transparent rounded-full mb-4 mx-auto"
                        ),
                        rx.el.p(
                            DownloaderState.status_label,
                            class_name="text-gray-500 text-center font-medium",
                        ),
                        class_name="flex flex-col items-center py-16",
                    ),
                    class_name="max-w-3xl mx-auto",
                ),
            ),
            rx.cond(
                DownloaderState.status == "ready",
                rx.el.section(
                    rx.el.div(
                        rx.el.div(
                            # Source context badge
                            rx.cond(
                                DownloaderState.result_source != "",
                                rx.el.div(
                                    rx.cond(
                                        DownloaderState.result_source == "url",
                                        rx.el.div(
                                            rx.icon("link", class_name="h-3.5 w-3.5 text-gray-400 shrink-0"),
                                            rx.el.span(
                                                DownloaderState.result_source_label,
                                                class_name="text-xs text-gray-400 truncate max-w-xs sm:max-w-lg",
                                            ),
                                            class_name="flex items-center gap-1.5",
                                        ),
                                        rx.cond(
                                            DownloaderState.result_source == "profile",
                                            rx.el.div(
                                                rx.icon("user", class_name="h-3.5 w-3.5 text-pink-400 shrink-0"),
                                                rx.el.span(
                                                    DownloaderState.result_source_label,
                                                    class_name="text-xs text-pink-600 font-semibold",
                                                ),
                                                class_name="flex items-center gap-1.5",
                                            ),
                                            rx.el.div(
                                                rx.icon("calendar", class_name="h-3.5 w-3.5 text-indigo-400 shrink-0"),
                                                rx.el.span(
                                                    DownloaderState.result_source_label,
                                                    class_name="text-xs text-indigo-600 font-semibold",
                                                ),
                                                class_name="flex items-center gap-1.5",
                                            ),
                                        ),
                                    ),
                                    class_name="mb-3",
                                ),
                                None,
                            ),
                            rx.el.div(
                                rx.el.p(
                                    f"Found {DownloaderState.media_items.length()} media items ({DownloaderState.video_count} videos, {DownloaderState.image_count} images)",
                                    class_name="text-gray-600 font-medium",
                                ),
                                rx.el.div(
                                    rx.el.button(
                                        "Select All",
                                        on_click=DownloaderState.select_all,
                                        class_name="text-sm font-semibold text-indigo-600 hover:text-indigo-800 transition-colors",
                                    ),
                                    rx.el.div(
                                        class_name="w-px h-4 bg-gray-200"
                                    ),
                                    rx.el.button(
                                        "Deselect All",
                                        on_click=DownloaderState.deselect_all,
                                        class_name="text-sm font-semibold text-gray-500 hover:text-gray-700 transition-colors",
                                    ),
                                    class_name="flex items-center gap-4",
                                ),
                                class_name="flex flex-col md:flex-row items-center justify-between gap-4 p-4 bg-gray-50 rounded-xl border border-gray-100 mb-6",
                            ),
                            rx.el.div(
                                rx.foreach(
                                    DownloaderState.media_items, media_card
                                ),
                                class_name="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 mb-12",
                            ),
                            rx.el.div(
                                rx.el.button(
                                    rx.icon(
                                        "cloud_download", class_name="h-6 w-6"
                                    ),
                                    f"Download Selected ({DownloaderState.selected_count})",
                                    on_click=DownloaderState.download_selected,
                                    disabled=DownloaderState.selected_count
                                    == 0,
                                    class_name="w-full sm:w-auto px-10 py-5 bg-indigo-600 text-white rounded-2xl font-bold text-lg hover:bg-indigo-700 transition-all shadow-xl shadow-indigo-100 disabled:opacity-50 disabled:shadow-none flex items-center justify-center gap-4",
                                ),
                                class_name="flex justify-center border-t border-gray-100 pt-10",
                            ),
                        ),
                        class_name="animate-in fade-in slide-in-from-bottom-4 duration-500",
                    ),
                    id="media-results",
                ),
                rx.cond(
                    DownloaderState.status == "idle",
                    rx.cond(
                        DownloaderState.active_tab == "url",
                        rx.el.div(
                            rx.el.div(
                                rx.icon(
                                    "inbox",
                                    class_name="h-16 w-16 text-gray-200 mb-4",
                                ),
                                rx.el.p(
                                    "Enter a story URL above to begin analysis",
                                    class_name="text-gray-400 font-medium",
                                ),
                                class_name="flex flex-col items-center justify-center py-24 border-2 border-dashed border-gray-100 rounded-3xl",
                            ),
                            class_name="max-w-3xl mx-auto",
                        ),
                        None,
                    ),
                    None,
                ),
            ),
            rx.el.footer(
                rx.el.div(
                    rx.el.div(
                        rx.el.p(
                            "Disclaimer: This tool is intended for personal use only. Users are responsible for ensuring they have the legal right to download content and must respect intellectual property rights.",
                            class_name="text-gray-400 text-xs text-center max-w-2xl mx-auto",
                        ),
                        class_name="mb-6",
                    ),
                    rx.el.p(
                        "This tool only downloads content you are authorized to view. No credentials are stored.",
                        class_name="text-gray-400 text-sm text-center mb-2",
                    ),
                    rx.el.p(
                        "© 2024 Story Downloader Pro. Not affiliated with Instagram.",
                        class_name="text-gray-300 text-xs text-center uppercase tracking-widest",
                    ),
                    class_name="mt-20 border-t border-gray-100 pt-8",
                )
            ),
            class_name="max-w-5xl mx-auto px-4 py-12",
        ),
        lightbox_modal(),
        class_name="min-h-screen bg-white font-['Inter']",
    )


app = rx.App(
    theme=rx.theme(appearance="light"),
    head_components=[
        rx.el.link(rel="preconnect", href="https://fonts.googleapis.com"),
        rx.el.link(
            rel="preconnect", href="https://fonts.gstatic.com", cross_origin=""
        ),
        rx.el.link(
            href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap",
            rel="stylesheet",
        ),
    ],
)

# Register the proxy download endpoint on the Reflex Starlette backend.
app._api.add_route("/proxy-download", proxy_download, methods=["GET"])

app.add_page(
    index,
    route="/",
    title="MiStories",
    on_load=[DownloaderState.load_session, DownloaderState.setup_client_scripts],
)