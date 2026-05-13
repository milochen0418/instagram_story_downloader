import reflex as rx
from instagram_story_downloader.states.downloader import DownloaderState, MediaItem


def media_card(item: MediaItem) -> rx.Component:
    return rx.el.div(
        # ── Thumbnail / hover-play area ──────────────────────────────
        rx.el.div(
            # Poster image
            rx.el.img(
                src=item["thumbnail_url"],
                class_name="absolute inset-0 h-full w-full object-cover",
            ),
            # Hidden video for hover-preview (video items only)
            rx.cond(
                item["type"] == "video",
                rx.el.video(
                    data_src=item["url"],
                    muted=True,
                    loop=True,
                    playsinline=True,
                    class_name="absolute inset-0 w-full h-full object-cover pointer-events-none",
                    style={"opacity": "0", "transition": "opacity 0.3s"},
                ),
                rx.fragment(),
            ),
            # Play icon overlay (video items only; fades out while video plays)
            rx.cond(
                item["type"] == "video",
                rx.el.div(
                    rx.icon("play", class_name="h-10 w-10 text-white opacity-80"),
                    class_name="play-icon-overlay absolute inset-0 flex items-center justify-center bg-black/20 pointer-events-none",
                    style={"transition": "opacity 0.3s"},
                ),
                None,
            ),
            # Transparent click layer — opens lightbox
            rx.el.div(
                class_name="absolute inset-0 z-10 cursor-pointer",
                on_click=lambda: DownloaderState.open_lightbox_for_item(item["id"]),
            ),
            # Date badge (bottom-left corner of thumbnail)
            rx.cond(
                item["date_label"] != "",
                rx.el.div(
                    item["date_label"],
                    class_name="absolute bottom-2 left-2 z-20 text-xs font-semibold text-white pointer-events-none",
                    style={"background": "rgba(0,0,0,0.55)", "borderRadius": "4px", "padding": "2px 6px", "backdropFilter": "blur(4px)"},
                ),
                rx.fragment(),
            ),
            class_name=rx.cond(
                item["type"] == "video",
                "vc-thumb relative overflow-hidden rounded-t-xl h-48",
                "relative overflow-hidden rounded-t-xl h-48",
            ),
        ),
        rx.el.div(
            rx.el.div(
                rx.el.div(
                    rx.el.input(
                        type="checkbox",
                        checked=item["selected"],
                        on_change=lambda _: (
                            DownloaderState.toggle_item_selection(item["id"])
                        ),
                        class_name="h-5 w-5 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 cursor-pointer",
                    ),
                    rx.el.span(
                        rx.match(
                            item["type"],
                            ("video", "Video"),
                            ("image", "Image"),
                            "Media",
                        ),
                        class_name=rx.cond(
                            item["type"] == "video",
                            "text-xs font-semibold px-2 py-0.5 rounded-full bg-blue-100 text-blue-700",
                            "text-xs font-semibold px-2 py-0.5 rounded-full bg-purple-100 text-purple-700",
                        ),
                    ),
                    class_name="flex items-center gap-3",
                ),
                class_name="mb-3",
            ),
            rx.cond(
                item["type"] == "video",
                rx.el.div(
                    rx.el.label(
                        "Quality", class_name="text-xs text-gray-500 block mb-1"
                    ),
                    rx.el.div(
                        rx.el.select(
                            rx.foreach(
                                item["qualities"],
                                lambda q, i: rx.el.option(
                                    q["label"], value=i.to_string()
                                ),
                            ),
                            value=item["selected_quality_index"].to_string(),
                            on_change=lambda val: (
                                DownloaderState.change_quality(item["id"], val)
                            ),
                            class_name="w-full text-sm p-1.5 border border-gray-200 rounded-lg bg-white appearance-none focus:ring-2 focus:ring-indigo-500 pr-8",
                        ),
                        rx.icon(
                            "chevron-down",
                            class_name="absolute right-2 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400 pointer-events-none",
                        ),
                        class_name="relative",
                    ),
                    class_name="mb-4",
                ),
                rx.el.div(class_name="h-[60px]"),
            ),
            rx.el.button(
                rx.icon("download", class_name="h-4 w-4"),
                "Download",
                on_click=lambda: DownloaderState.download_single(item["id"]),
                class_name="w-full flex items-center justify-center gap-2 py-2 text-sm font-medium text-gray-700 bg-gray-50 border border-gray-200 rounded-lg hover:bg-gray-100 transition-colors",
            ),
            class_name="p-4",
        ),
        class_name="bg-white border border-gray-100 rounded-xl overflow-hidden hover:shadow-md transition-all duration-300 animate-in fade-in zoom-in-95",
    )