import reflex as rx
from instagram_story_downloader.states.downloader import DownloaderState, MediaItem


def media_card(item: MediaItem) -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.cond(
                item["type"] == "video",
                rx.el.div(
                    rx.icon(
                        "play", class_name="h-10 w-10 text-white opacity-80"
                    ),
                    class_name="absolute inset-0 flex items-center justify-center bg-black/20",
                ),
                None,
            ),
            rx.el.img(
                src=item["thumbnail_url"],
                class_name="h-48 w-full object-cover transition-transform duration-500 hover:scale-110",
            ),
            class_name="relative overflow-hidden rounded-t-xl",
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