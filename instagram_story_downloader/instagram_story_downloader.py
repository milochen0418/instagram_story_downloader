import urllib.parse
import httpx
import reflex as rx
from starlette.requests import Request
from starlette.responses import StreamingResponse, JSONResponse
from instagram_story_downloader.states.downloader import (
    DownloaderState,
    ArchiveMonthItem,
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
    """Full-screen lightbox player for previewing media items."""
    return rx.cond(
        DownloaderState.lightbox_open,
        rx.el.div(
            # Backdrop — click closes the modal
            rx.el.div(
                class_name="absolute inset-0 z-0 cursor-pointer",
                on_click=DownloaderState.close_lightbox,
            ),
            # Floating content panel (higher z-index than backdrop, so clicks stay here)
            rx.el.div(
                # ── Top bar: counter + close ─────────────────────
                rx.el.div(
                    rx.el.span(
                        DownloaderState.lightbox_counter,
                        class_name="text-white/60 text-sm font-medium tabular-nums",
                    ),
                    rx.el.button(
                        rx.icon("x", class_name="h-5 w-5"),
                        on_click=DownloaderState.close_lightbox,
                        class_name="text-white/70 hover:text-white p-2 rounded-full hover:bg-white/10 transition-colors",
                        title="Close (Esc)",
                    ),
                    class_name="flex items-center justify-between px-4 py-3 shrink-0",
                ),
                # ── Media player ─────────────────────────────────
                rx.el.div(
                    rx.cond(
                        DownloaderState.lightbox_item["type"] == "video",
                        rx.el.video(
                            src=DownloaderState.lightbox_item["url"],
                            controls=True,
                            autoplay=True,
                            loop=False,
                            class_name="max-h-[72vh] max-w-full rounded-lg shadow-2xl",
                            id="lightbox-video",
                        ),
                        rx.el.img(
                            src=DownloaderState.lightbox_item["url"],
                            class_name="max-h-[72vh] max-w-full object-contain rounded-lg shadow-2xl",
                        ),
                    ),
                    class_name="flex items-center justify-center px-4 flex-1 min-h-0",
                ),
                # ── Bottom bar: prev / filename / next ───────────
                rx.el.div(
                    rx.el.button(
                        rx.icon("chevron-left", class_name="h-6 w-6"),
                        on_click=DownloaderState.lightbox_prev,
                        disabled=~DownloaderState.lightbox_has_prev,
                        class_name="text-white/70 hover:text-white p-3 rounded-full hover:bg-white/10 transition-colors disabled:opacity-25 disabled:cursor-not-allowed",
                        title="Previous (←)",
                    ),
                    rx.el.p(
                        DownloaderState.lightbox_item["filename"],
                        class_name="text-white/40 text-xs truncate max-w-xs text-center",
                    ),
                    rx.el.button(
                        rx.icon("chevron-right", class_name="h-6 w-6"),
                        on_click=DownloaderState.lightbox_next,
                        disabled=~DownloaderState.lightbox_has_next,
                        class_name="text-white/70 hover:text-white p-3 rounded-full hover:bg-white/10 transition-colors disabled:opacity-25 disabled:cursor-not-allowed",
                        title="Next (→)",
                    ),
                    class_name="flex items-center justify-between px-4 py-3 shrink-0",
                ),
                id="lightbox-wrapper",
                class_name="relative z-10 flex flex-col w-full max-w-3xl mx-4 max-h-screen",
            ),
            class_name="fixed inset-0 flex items-center justify-center bg-black/92",
            style={"zIndex": "9999"},
        ),
        rx.fragment(),
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
                            "shield-check", class_name="h-8 w-8 text-indigo-600"
                        ),
                        rx.el.h1(
                            "Instagram Story Downloader",
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
                        rx.el.form(
                            rx.el.div(
                                rx.el.div(
                                    rx.icon(
                                        "link",
                                        class_name="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400",
                                    ),
                                    rx.el.input(
                                        name="story_url",
                                        placeholder="Paste Instagram Story or Archive URL here...",
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
                                        "Analyze Story",
                                    ),
                                    type="submit",
                                    disabled=DownloaderState.is_loading,
                                    class_name="px-8 py-4 bg-indigo-600 text-white rounded-xl font-semibold hover:bg-indigo-700 transition-colors disabled:opacity-70 disabled:cursor-not-allowed whitespace-nowrap shadow-lg shadow-indigo-100",
                                ),
                                class_name="flex flex-col sm:flex-row gap-4",
                            ),
                            on_submit=DownloaderState.handle_submit,
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
                                        rx.el.div(
                                            rx.icon("calendar", class_name="h-3.5 w-3.5 text-indigo-400 shrink-0"),
                                            rx.el.span(
                                                DownloaderState.result_source_label,
                                                class_name="text-xs text-indigo-600 font-semibold",
                                            ),
                                            class_name="flex items-center gap-1.5",
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
    on_load=[DownloaderState.load_session, DownloaderState.setup_client_scripts],
)