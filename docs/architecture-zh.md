# Instagram Story Downloader — 技術架構說明文件

## 目錄

1. [整體架構概覽](#整體架構概覽)
2. [技術堆疊](#技術堆疊)
3. [突破 Instagram 認證保護的核心機制](#突破-instagram-認證保護的核心機制)
4. [完整資料流程：從輸入 URL 到下載完成](#完整資料流程從輸入-url-到下載完成)
5. [各模組詳解](#各模組詳解)
6. [前後端通訊架構](#前後端通訊架構)
7. [安全性設計考量](#安全性設計考量)

---

## 整體架構概覽

本程式是一個全端 Web 應用程式，讓使用者能夠透過瀏覽器介面下載 Instagram 限時動態（Stories）。其核心挑戰在於：**Instagram 的限時動態只有登入的用戶、且必須是該帳號的關注者才能查看**，這意味著一般的直接 HTTP 請求會因未授權而失敗。

本程式的解法是**借用使用者本機瀏覽器中已存在的 Instagram 登入 Cookie**，藉此完全跳過重新登入的需求，以合法的已認證身分向 Instagram 發出請求。

```
使用者                  Web 前端 (React)          Python 後端 (Starlette)
  │                          │                            │
  │  輸入 Story URL           │                            │
  │─────────────────────────>│                            │
  │                          │  WebSocket 事件傳遞         │
  │                          │───────────────────────────>│
  │                          │              讀取本機瀏覽器 Cookie
  │                          │              用 yt-dlp 解析媒體資訊
  │                          │              取得簽名 CDN URL
  │                          │<───────────────────────────│
  │  顯示媒體列表             │                            │
  │<─────────────────────────│                            │
  │  點擊下載                 │                            │
  │─────────────────────────>│  JS 觸發 /proxy-download   │
  │                          │───────────────────────────>│
  │                          │              向 Instagram CDN 串流
  │<═════════════════════════════════════════════════════│  (檔案串流回傳)
  │  檔案儲存到本機           │                            │
```

---

## 技術堆疊

| 層次 | 技術 | 用途 |
|------|------|------|
| 前端框架 | [Reflex](https://reflex.dev/) → React | 以 Python 撰寫 UI，編譯成 React 元件 |
| 後端框架 | Starlette (ASGI) | Reflex 底層的非同步 HTTP 伺服器 |
| 媒體提取 | [yt-dlp](https://github.com/yt-dlp/yt-dlp) | 從 Instagram 解析媒體資訊、讀取瀏覽器 Cookie |
| HTTP 客戶端 | [httpx](https://www.python-httpx.org/) | 非同步串流代理 CDN 請求 |
| 狀態管理 | `rx.State`（Reflex 內建） | 前後端共享狀態，透過 WebSocket 同步 |

---

## 突破 Instagram 認證保護的核心機制

### 問題：Instagram 如何保護限時動態

Instagram 透過以下機制保護私人內容：

1. **HTTP Cookie 驗證**：所有 API 請求必須帶有有效的 `sessionid` 和 `ds_user_id` Cookie，這兩個 Cookie 是登入後 Instagram 服務器頒發的 Session Token。
2. **簽名 CDN URL**：即使取得了媒體的直接連結，URL 也帶有時效性的加密簽名參數（token），過期後便無法使用。
3. **CORS 限制**：Instagram CDN（`fbcdn.net`、`cdninstagram.com`）設有跨來源資源共享限制，不允許任意第三方網站直接從瀏覽器抓取媒體檔案。

### 解法：借用本機瀏覽器的 Cookie

這是本程式最核心的突破點，整個流程完全在**使用者自己的電腦本機**執行：

```python
# states/downloader.py
_BROWSERS_TO_TRY = ["chrome", "firefox", "safari", "edge", "chromium", "brave"]

def _check_browser_has_instagram_cookies(browser: str) -> bool:
    """回傳 True 表示該瀏覽器存有 Instagram 的 Session Cookie"""
    ydl_opts = {
        "cookiesfrombrowser": (browser,),  # 關鍵參數：指示 yt-dlp 讀取哪個瀏覽器的 Cookie
        "quiet": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for cookie in ydl.cookiejar:
            if "instagram.com" in cookie.domain and cookie.name in ("sessionid", "ds_user_id"):
                return True
    return False
```

**`cookiesfrombrowser` 的運作原理**：

yt-dlp 使用 `browser_cookie3` 等底層函式庫，直接讀取瀏覽器在本機磁碟上的 Cookie 資料庫（SQLite 格式）。這些 Cookie 檔案的路徑因瀏覽器和作業系統而異：

- **Chrome（macOS）**：`~/Library/Application Support/Google/Chrome/Default/Cookies`
- **Firefox（macOS）**：`~/Library/Application Support/Firefox/Profiles/*.default/cookies.sqlite`
- **Safari**：需要完整磁碟存取權限（Full Disk Access），因此排在嘗試清單最後

程式會**依序嘗試**每個瀏覽器，找到第一個有 Instagram Session 的瀏覽器就使用它：

```python
def extract_info() -> tuple[dict, str]:
    for browser in _BROWSERS_TO_TRY:
        try:
            info = _extract_with_browser(url, browser)  # 用該瀏覽器的 Cookie 發出請求
            if info:
                return info, browser
        except Exception:
            continue
    # 最後嘗試不帶 Cookie（公開內容）
    ...
```

### 為什麼這樣做不需要使用者輸入帳號密碼？

因為使用者已經在自己的瀏覽器中登入過 Instagram，瀏覽器幫使用者存好了認證 Cookie。本程式只是讓後端 Python 程序代為讀取並使用這些 Cookie——**等同於以使用者的瀏覽器身分發出請求**，完全不需要處理、儲存任何密碼。

---

## 完整資料流程：從輸入 URL 到下載完成

### 階段一：URL 解析與驗證

使用者貼入的 URL 格式必須為：
```
https://www.instagram.com/stories/<username>/<media_id>/
```

後端使用正規表示式提取出 `username` 和 `media_id`：

```python
match = re.search(r"instagram\.com/stories/([^/]+)/(\d+)", url)
username = match.group(1)
media_id = match.group(2)
```

### 階段二：透過 yt-dlp 提取媒體資訊

yt-dlp 不只是下載工具，它內建了 Instagram 的 Extractor 模組（`InstagramIE`），可以：

1. 根據 `media_id` 構造正確的 Instagram API/GraphQL 請求
2. 將讀取到的瀏覽器 Cookie 附加到請求的 HTTP Header 中
3. 解析 Instagram 回傳的 JSON 結構，提取媒體的 CDN URL

回傳的資料結構包含：
- `formats`：不同解析度的媒體格式清單，每個含有簽名 CDN URL
- `thumbnails`：縮圖 URL 清單
- `_type`：`"playlist"`（多張 Story）或單一物件

### 階段三：格式選擇與品質分級

```python
def _build_media_item(entry: dict, username: str, media_id: str) -> MediaItem:
```

媒體格式的選擇有三個優先順序：

1. **優先：Combined MP4**（影片 + 音訊合併的完整 MP4 檔案）
   - 條件：`vcodec is None`（表示已合併，無需分開的 codec）且 `ext == "mp4"` 且 `protocol == "https"`
   - 依解析度（`height`）由高到低排序，最多取 3 個品質選項

2. **次要：DASH 影片串流**（僅影片無音訊）
   - 條件：有 `vcodec` 且不為 `"none"`
   - 適用於 yt-dlp 無法找到合併格式的情況

3. **最後：圖片**
   - 無任何影片格式時，提取靜態圖片 URL

### 階段四：前端展示媒體卡片

後端狀態更新後，Reflex 透過 WebSocket 將 `media_items` 清單同步到前端，React 以 `rx.foreach` 迴圈渲染每張 `media_card`：

- 每個卡片顯示縮圖、媒體類型標籤、品質下拉選單
- 勾選框讓使用者選擇要批次下載的項目

### 階段五：下載觸發

這是架構中最有技巧性的部分，需要繞過兩個限制：

**限制 1：CDN URL 不允許跨域直接存取（CORS）**
**限制 2：Reflex 前端跑在 Port 3000（Vite dev server），無法路由自訂 API**

解法是透過**後端代理（Proxy）**串流下載：

#### Step 1：前端執行 JavaScript 觸發下載

```python
def _trigger_download_script(cdn_url: str, filename: str) -> str:
    backend = get_config().api_url.rstrip("/")  # 指向 Port 8000 的 Python 後端
    params = urllib.parse.urlencode({"url": cdn_url, "filename": filename})
    full_url = f"{backend}/proxy-download?{params}"
    # 建立隱形的 <a> 標籤並模擬點擊，觸發瀏覽器的原生下載行為
    return (
        f"var _a=document.createElement('a');"
        f"_a.href='{safe_url}';"
        f"_a.download='{safe_fn}';"
        f"document.body.appendChild(_a);"
        f"_a.click();"
        f"document.body.removeChild(_a);"
    )
```

`rx.call_script(...)` 讓後端可以命令前端執行任意 JavaScript，這段 JS 在使用者瀏覽器中建立一個看不見的連結元素並點擊它，瀏覽器便會對 Port 8000 的 `/proxy-download` 發出 GET 請求。

#### Step 2：後端代理端點串流 CDN 內容

```python
# instagram_story_downloader.py
async def proxy_download(request: Request):
    url = request.query_params.get("url", "")
    filename = request.query_params.get("filename", "download")
    
    # 白名單驗證：只允許 Instagram 的合法 CDN 主機
    parsed = urllib.parse.urlparse(url)
    if not any(parsed.netloc.endswith(h) for h in _ALLOWED_CDN_HOSTS):
        return JSONResponse({"error": "URL not allowed"}, status_code=400)
    
    # 以後端身分向 Instagram CDN 發出 HTTP 請求（不受 CORS 限制）
    client = httpx.AsyncClient(follow_redirects=True, timeout=60)
    upstream = await client.send(client.build_request("GET", url), stream=True)
    
    # 設定 Content-Disposition 讓瀏覽器以下載模式處理
    headers = {"Content-Disposition": f'attachment; filename="{safe_filename}"'}
    
    # 以 65 KB 為單位逐塊串流，避免在記憶體中存放整個檔案
    async def _stream():
        async for chunk in upstream.aiter_bytes(65536):
            yield chunk
    
    return StreamingResponse(_stream(), media_type=content_type, headers=headers)
```

**為什麼後端能成功？** 因為 CORS 是瀏覽器層面的限制，不適用於伺服器對伺服器的請求。Python 後端直接向 CDN 發出 HTTP GET，Instagram CDN 只驗證 URL 的簽名是否有效（已在 yt-dlp 提取階段取得），不再需要 Cookie。

---

## 各模組詳解

```
instagram_story_downloader/
├── instagram_story_downloader.py   # 應用程式入口：UI 定義 + proxy 端點 + app 設定
├── states/
│   └── downloader.py               # 核心邏輯：狀態管理、媒體提取、下載觸發
└── components/
    └── media_card.py               # 可重用 UI 元件：單張媒體卡片
```

### `instagram_story_downloader.py` — 應用入口

- 定義 `index()` 函式，描述整個頁面的 React 元件樹（以 Python DSL 撰寫）
- 註冊自訂 Starlette 路由 `/proxy-download`，讓它跑在 Reflex 的 ASGI 應用之上
- 建立 `rx.App` 實例並掛載頁面

### `states/downloader.py` — 核心業務邏輯

包含兩個主要部分：

**純函式（無狀態）**：
- `_check_browser_has_instagram_cookies(browser)` — 偵測瀏覽器是否有 Instagram Cookie
- `_extract_with_browser(url, browser)` — 用指定瀏覽器的 Cookie 呼叫 yt-dlp 提取媒體資訊
- `_build_media_item(entry, username, media_id)` — 將 yt-dlp 原始資料轉換成 `MediaItem` 資料結構
- `_trigger_download_script(cdn_url, filename)` — 產生觸發瀏覽器下載的 JavaScript 字串

**`DownloaderState`（有狀態，繼承 `rx.State`）**：

| 事件 | 說明 |
|------|------|
| `load_session` | 頁面載入時非同步偵測瀏覽器 Cookie |
| `handle_submit` | 使用者送出 URL 表單，觸發媒體解析流程 |
| `toggle_item_selection` | 切換單一媒體的勾選狀態 |
| `select_all / deselect_all` | 批次全選/全不選 |
| `change_quality` | 使用者切換品質選項 |
| `download_selected` | 批次下載所有已勾選的媒體 |
| `download_single` | 下載單一媒體卡片 |

### `components/media_card.py` — 媒體卡片元件

純 UI 元件，接收單個 `MediaItem` TypedDict，渲染成：
- 縮圖預覽（影片顯示播放 icon overlay）
- 影片/圖片類型標籤
- 品質下拉選單（僅影片）
- 個別下載按鈕

---

## 前後端通訊架構

Reflex 使用 **WebSocket** 作為前後端通訊的主要通道，這不同於傳統的 REST API 架構：

```
瀏覽器 (React)                          Python 後端 (Starlette)
    │                                           │
    │   WebSocket 連線（ws://localhost:8000）    │
    │<══════════════════════════════════════════│
    │                                           │
    │  用戶操作 → rx.Event（序列化）→ WS 傳送    │
    │──────────────────────────────────────────>│
    │                          執行 State event handler
    │                          修改 State 屬性
    │  State diff（只傳遞變更部分）← WS 回傳    │
    │<──────────────────────────────────────────│
    │  React 重新渲染受影響的元件               │
```

**特殊機制：`yield` 中間狀態更新**

在 `handle_submit` 中使用 `yield` 可以在非同步操作進行中即時更新 UI：

```python
self.status = "analyzing"
yield  # 立刻將 "analyzing" 狀態推送到前端（顯示 loading 動畫）
# ... 執行耗時的 yt-dlp 提取 ...
self.status = "ready"
# handler 結束時自動推送最終狀態
```

**`rx.call_script` 的反向控制**

後端可以主動命令前端執行 JavaScript，用於觸發無法在伺服器端完成的瀏覽器行為（如呼叫原生下載 API）：

```python
yield rx.call_script(_trigger_download_script(cdn_url, filename))
```

---

## 安全性設計考量

### CDN 主機白名單

代理端點只接受特定 CDN 主機的 URL，防止被惡意利用來代理任意網址（SSRF 防護）：

```python
_ALLOWED_CDN_HOSTS = (
    ".fbcdn.net",
    ".cdninstagram.com",
    "instagram.com",
)
```

### 無憑證儲存

本程式**從不儲存任何 Instagram 帳號、密碼或 Session Token**。Cookie 只在記憶體中短暫存在於 yt-dlp 的請求週期內，不寫入任何檔案。

### 本機執行原則

整個應用程式設計為在使用者本機執行（`localhost`）。後端讀取的 Cookie 是使用者自己的瀏覽器 Cookie，不涉及任何第三方服務器中轉。

---

*本文件描述的技術僅供教育目的。使用者應確保自己有權下載相關內容，並遵守 Instagram 服務條款及適用的智慧財產權法律。*
