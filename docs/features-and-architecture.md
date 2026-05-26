# MiStories — 功能與架構文件

> 最後更新：2026-05-27

---

## 目錄

1. [專案概覽](#專案概覽)
2. [核心功能](#核心功能)
3. [技術堆疊](#技術堆疊)
4. [專案結構](#專案結構)
5. [架構概覽](#架構概覽)
6. [認證機制：借用本機瀏覽器 Cookie](#認證機制借用本機瀏覽器-cookie)
7. [三種媒體抓取模式](#三種媒體抓取模式)
8. [後端代理下載](#後端代理下載)
9. [狀態管理 (DownloaderState)](#狀態管理-downloaderstate)
10. [UI 元件](#ui-元件)
11. [安全性設計](#安全性設計)
12. [已知限制](#已知限制)

---

## 專案概覽

**MiStories** 是一個以 [Reflex](https://reflex.dev/) 打造的全端 Web 應用程式，讓使用者能夠在本機瀏覽器上預覽並下載自己的 Instagram 限時動態（Stories）、精選動態（Highlights）、以及封存的限時動態（Archive）。

整個應用執行在使用者的**本機**，不需要任何第三方伺服器或帳號密碼輸入。

---

## 核心功能

### 1. 單一 URL 解析
貼入任意 Instagram Story 或 Highlight 連結，自動解析媒體清單：

- `https://www.instagram.com/stories/username/12345/` → 單則限時動態
- `https://www.instagram.com/stories/highlights/98765/` → 完整精選動態合集

### 2. Profile 瀏覽器
貼入使用者個人頁面網址（`instagram.com/username/`），應用程式會：

1. 解析該使用者的 **今日限時動態**（若有）
2. 列出所有 **精選動態（Highlights）**，附帶封面縮圖與項目數量
3. 點擊任一類別卡片，載入該分類下的所有媒體

### 3. 封存瀏覽器（Archive Browser）
切換至「Browse Archive」分頁，可瀏覽自己帳號的封存限時動態：

1. 點擊「Load My Archive」：以 Playwright 開啟 `instagram.com/archive/stories/` 並攔截 `day_shells` API 回應
2. 依**年月**分組顯示月份卡片，每張卡片顯示該月故事數量
3. 點擊月份卡片，批次載入該月所有媒體項目

### 4. 媒體卡片 Grid
解析完成後，所有媒體以 Grid 排列顯示：

- **縮圖預覽**：靜止縮圖 + 滑鼠懸停自動播放影片預覽
- **類型徽章**：`Video`（藍色）或 `Image`（紫色）
- **日期標籤**：顯示於縮圖左下角（格式：`May 14, 2025`）
- **畫質選擇**：影片支援多畫質下拉選單（如 `1080p`、`720p`、縮圖）
- **單項下載**：每張卡片均有獨立下載按鈕
- **全選 / 取消全選**：批量選取控制

### 5. 批次下載
選取多個媒體項目後，點擊「Download Selected (N)」，所有檔案依序透過後端代理串流至本機。

### 6. 浮動燈箱（Lightbox）播放器
點擊任意媒體縮圖，開啟浮動播放器視窗：

- **可拖曳**：拖動標題列自由移動視窗位置
- **可調整大小**：使用 CSS `resize: both` 調整視窗尺寸
- **鍵盤導覽**：`←` / `→` 切換媒體，`Esc` 關閉
- **計數器**：顯示目前項目位置（如 `3 / 12`）
- **日期標籤**：顯示拍攝日期

### 7. Session 狀態偵測
頁面載入時自動掃描本機瀏覽器（Chrome、Firefox、Safari、Edge、Chromium、Brave），若找到有效的 Instagram 登入 Session，頁面頂端顯示綠色徽章；否則顯示警告提示使用者先登入。

---

## 技術堆疊

| 層次 | 技術 | 版本 | 用途 |
|------|------|------|------|
| UI 框架 | [Reflex](https://reflex.dev/) | 0.8.26 | Python 撰寫 UI，編譯成 React 元件 |
| 樣式 | Tailwind CSS v3 | — | 透過 `TailwindV3Plugin` 整合 |
| 後端 ASGI | Starlette | — | Reflex 底層 HTTP 伺服器 |
| 媒體解析 | [yt-dlp](https://github.com/yt-dlp/yt-dlp) | latest | 解析 IG Story URL、讀取瀏覽器 Cookie |
| 瀏覽器自動化 | [Playwright](https://playwright.dev/) | ^1.59 | 繞過 bot 偵測、存取封存 API |
| HTTP 客戶端 | httpx | — | 非同步串流代理 CDN 請求 |
| Python 版本 | CPython | ~3.11 | 專案指定版本 |
| 套件管理 | Poetry | — | 依賴管理與虛擬環境 |

---

## 專案結構

```
instagram_story_downloader/
├── instagram_story_downloader/
│   ├── __init__.py
│   ├── instagram_story_downloader.py   # 主頁面、路由、UI 元件組合
│   ├── components/
│   │   ├── __init__.py
│   │   └── media_card.py               # 媒體卡片元件
│   └── states/
│       ├── __init__.py
│       └── downloader.py               # 核心狀態機 + 所有 API/Playwright 邏輯
├── assets/
│   └── __init__.py
├── docs/
│   ├── architecture-zh.md              # 深度技術架構說明（中文）
│   └── features-and-architecture.md   # 本文件
├── rxconfig.py                         # Reflex 設定（app name、Tailwind plugin）
├── pyproject.toml                      # Poetry 依賴設定
├── reflex_rerun.sh                     # 開發用啟動腳本
├── proj_reinstall.sh                   # 完整環境重建腳本
├── AGENTS.md                           # AI agent 與開發者工作流程規範
└── README.md                           # 快速上手指南
```

---

## 架構概覽

```
使用者瀏覽器 (React SPA)
        │
        │  WebSocket (Reflex 狀態同步)
        ▼
Python 後端 (Starlette / Reflex)
  ├── DownloaderState (rx.State)
  │     ├── handle_submit()         ← URL 輸入分流
  │     ├── load_archive_months()   ← 封存月份清單
  │     ├── select_archive_month()  ← 月份媒體批次載入
  │     ├── select_profile_category() ← 個人頁分類載入
  │     └── download_selected()    ← 觸發瀏覽器下載
  │
  ├── /proxy-download (Starlette route)
  │     └── proxy_download()       ← CDN 串流代理
  │
  ├── yt-dlp                        ← Story/Highlight URL 解析
  └── Playwright (headless Chromium)
        ├── _fetch_day_shells()     ← 封存日清單
        ├── _fetch_reels_by_ids()   ← 批次媒體內容
        └── _fetch_profile_info()   ← 個人頁 Stories + Highlights
```

### 資料流：URL 解析到下載

```
① 使用者輸入 URL
        │
        ▼
② handle_submit() 路由判斷
   ├─ archive URL     → 切換至 Archive 分頁
   ├─ profile URL     → _fetch_profile_info() via Playwright
   └─ story URL       → yt-dlp 或 Playwright 解析
        │
        ▼
③ _build_media_item() 統一轉換格式
   （combined mp4 → DASH video → image 優先順序）
        │
        ▼
④ media_items 更新 → React 渲染媒體卡片 Grid
        │
        ▼
⑤ 使用者點擊下載 → _trigger_download_script()
   → JS 建立隱形 <a> 標籤 → 呼叫 /proxy-download
        │
        ▼
⑥ proxy_download() 驗證 CDN host → httpx 串流回傳
```

---

## 認證機制：借用本機瀏覽器 Cookie

Instagram 的限時動態需要有效的 `sessionid` + `ds_user_id` Cookie 才能存取。本應用**不要求使用者輸入帳密**，而是直接讀取本機瀏覽器已有的登入 Session。

### 瀏覽器嘗試順序

```python
_BROWSERS_TO_TRY = ["chrome", "firefox", "safari", "edge", "chromium", "brave"]
```

以 Chrome 優先（Safari 在 macOS 需要完整磁碟存取權限，排最後）。

### 運作方式

yt-dlp 使用 `cookiesfrombrowser` 參數，透過底層 `browser_cookie3` 函式庫讀取各瀏覽器的 SQLite Cookie 資料庫：

| 瀏覽器 | macOS Cookie 路徑 |
|--------|------------------|
| Chrome | `~/Library/Application Support/Google/Chrome/Default/Cookies` |
| Firefox | `~/Library/Application Support/Firefox/Profiles/*.default/cookies.sqlite` |
| Safari | 需要 Full Disk Access 系統權限 |

### Playwright 的 Cookie 注入

封存和個人頁功能需要 Playwright headless Chromium。Cookie 以特定格式注入到 Playwright 的 browser context，並隱藏 `navigator.webdriver` 屬性以避免 bot 偵測：

```python
ctx.add_init_script(
    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
)
ctx.add_cookies(_pw_cookies(cookies))
```

---

## 三種媒體抓取模式

### 模式 A：直接 URL（yt-dlp）

適用情況：一般 Story URL (`/stories/username/id/`) 和 Highlight URL (`/stories/highlights/id/`)

- 直接呼叫 `yt-dlp.extract_info(url)`，帶入瀏覽器 Cookie
- 支援 playlist（多項目 Highlight）和單一媒體
- 依序嘗試所有瀏覽器，最後嘗試不帶 Cookie

### 模式 B：封存 API（Playwright）

適用情況：封存限時動態（`/archive/stories/`）

Instagram 直接的 HTTP 請求會被 bot 偵測攔截，必須透過 Playwright：

1. `_fetch_day_shells()`：開啟 `instagram.com/archive/stories/`，攔截頁面自動觸發的 `day_shells` API 回應（回應格式為 `for(;;);{...}` XSSI 前綴 JSON）
2. `_fetch_reels_by_ids()`：在同一頁面的 JS context 中發出 in-page `fetch()` 呼叫 `/api/v1/feed/reels_media/?reel_ids=...`，每批最多 20 個 reel ID

### 模式 C：個人頁 API（Playwright）

適用情況：個人頁 URL (`instagram.com/username/`)

`_fetch_profile_info()` 在頁面 JS context 中依序呼叫三個 API：

| 步驟 | API | 目的 |
|------|-----|------|
| 1 | `/api/v1/users/web_profile_info/?username=` | 取得數字 user_id |
| 2 | `/api/v1/feed/reels_media/?reel_ids=<user_id>` | 取得今日 Stories |
| 3 | `/api/v1/highlights/<user_id>/highlights_tray/` | 取得 Highlights 清單 |

封面縮圖由後端 Python 同步下載並轉換為 base64 data URI（繞過瀏覽器 CORS 限制），使用 `ThreadPoolExecutor(max_workers=6)` 並行處理。

---

## 後端代理下載

直接讓瀏覽器下載 Instagram CDN URL 會因 CORS 限制失敗。本應用透過後端代理解決此問題：

### `/proxy-download` 路由

```
GET /proxy-download?url=<CDN_URL>&filename=<檔名>
```

安全驗證（allowlist）：

```python
_ALLOWED_CDN_HOSTS = (
    ".fbcdn.net",
    ".cdninstagram.com",
    "instagram.com",
)
```

只有來自上述 CDN host 的 URL 才允許代理，其餘一律回傳 `400 Bad Request`。

### 下載觸發機制

後端產生一段 JS 程式碼，建立隱形 `<a>` 標籤並程式化點擊，指向後端代理 URL（port 8000）：

```javascript
var _a = document.createElement('a');
_a.href = 'http://localhost:8000/proxy-download?url=...&filename=...';
_a.download = 'filename';
document.body.appendChild(_a);
_a.click();
document.body.removeChild(_a);
```

使用後端 URL（port 8000）而非前端開發伺服器（port 3000），確保請求正確路由到 Starlette。

---

## 狀態管理 (DownloaderState)

`DownloaderState` 繼承 `rx.State`，所有狀態欄位透過 WebSocket 自動同步至前端。

### 主要狀態欄位

| 欄位 | 型別 | 說明 |
|------|------|------|
| `status` | `str` | `idle` / `analyzing` / `ready` / `error` |
| `media_items` | `list[MediaItem]` | 已解析的媒體項目清單 |
| `is_loading` | `bool` | 全域載入狀態 |
| `active_tab` | `str` | `url` 或 `archive` |
| `session_loaded` | `bool` | 是否偵測到瀏覽器 Session |
| `session_username` | `str` | 找到 Session 的瀏覽器名稱 |
| `archive_months` | `list[ArchiveMonthItem]` | 封存月份清單 |
| `archive_status` | `str` | `idle` / `loading_months` / `ready_months` / `error_months` |
| `profile_categories` | `list[ProfileCategoryItem]` | 個人頁分類清單 |
| `profile_status` | `str` | `idle` / `loading` / `ready` / `error` |
| `lightbox_open` | `bool` | 燈箱是否開啟 |
| `lightbox_index` | `int` | 目前燈箱顯示的媒體索引 |
| `result_source` | `str` | `url` / `archive` / `profile` |

### 核心型別定義

```python
class MediaItem(TypedDict):
    id: str
    type: str              # "video" | "image"
    url: str               # 目前選取畫質的 CDN URL
    thumbnail_url: str
    filename: str          # 預設下載檔名
    selected: bool
    qualities: list[QualityDict]   # 可用畫質選項
    selected_quality_index: int
    taken_at: int          # Unix timestamp
    date_label: str        # 如 "May 14, 2025"

class ArchiveMonthItem(TypedDict):
    year_month: str        # "2024-01"
    label: str             # "January 2024"
    count: int
    story_urls: list[str]  # archiveDay:XXX reel IDs

class ProfileCategoryItem(TypedDict):
    id: str                # numeric user_id 或 "highlight:XXX"
    label: str             # "Today's Stories" 或 Highlight 標題
    count: int
    cover_url: str         # base64 data URI
    category_type: str     # "stories" | "highlight"
```

### `_build_media_item()` 媒體格式優先順序

解析 yt-dlp 或 Playwright 回傳的 entry 時，依以下優先順序提取媒體 URL：

1. **Combined MP4**（`vcodec=None`、`protocol=https`）— Instagram 的完整影音合併串流，最優先
2. **DASH Video**（有 `vcodec`）— 僅影像軌道，音訊分離
3. **Image**（無影像格式）— 靜態圖片或縮圖

---

## UI 元件

### `instagram_story_downloader.py`（主頁面）

| 函式 | 說明 |
|------|------|
| `index()` | 主頁面根元件，包含 header、分頁、媒體 grid |
| `lightbox_modal()` | 浮動燈箱播放器（固定定位、可拖曳、可縮放） |
| `profile_browser_section()` | 個人頁分類 grid（顯示於 URL 分頁） |
| `profile_category_card()` | 單一分類卡片（Today's Stories 或 Highlight） |
| `archive_browser_section()` | 封存月份瀏覽 panel |
| `archive_month_card()` | 單一月份卡片，點擊觸發月份媒體載入 |
| `proxy_download()` | Starlette 路由 handler，串流代理 CDN 下載 |

### `components/media_card.py`

| 功能 | 實作方式 |
|------|---------|
| 縮圖顯示 | `<img>` absolute fill |
| 懸停播放預覽 | `<video data-src="...">` + JS `mouseover`/`mouseout` 事件（`setup_client_scripts`） |
| 播放圖示淡出 | `.play-icon-overlay` CSS transition |
| 日期標籤 | 縮圖左下角 badge，backdrop-filter blur |
| 畫質選擇器 | `<select>` 綁定 `DownloaderState.change_quality()` |
| 燈箱開啟 | 透明 `<div>` click layer，觸發 `open_lightbox_for_item()` |

---

## 安全性設計

| 威脅 | 防護措施 |
|------|---------|
| SSRF / 任意 URL 代理 | `/proxy-download` 強制驗證 `netloc` 須為 `_ALLOWED_CDN_HOSTS` 內的 host |
| 檔名注入 | 使用 `urllib.parse.quote()` 對 `Content-Disposition` 標頭的檔名進行 URL 編碼 |
| 帳號密碼外洩 | 完全不要求使用者輸入帳密；只讀取已在瀏覽器登入的 Cookie |
| XSS（JS 注入） | JS 程式碼中的 URL 與檔名以 `replace("'", "%27")` 和 `replace("'", "\'")` 處理引號 |
| Bot 偵測 | 注入 `navigator.webdriver` override，使用真實 Chrome User-Agent |

---

## 已知限制

- **macOS 限定**：Cookie 路徑和 Playwright 設定針對 macOS 測試；Linux/Windows 未驗證
- **Safari 需要額外授權**：需要在「系統偏好設定 → 安全性與隱私 → 完整磁碟存取」中授予 Terminal 權限
- **私人帳號**：若使用者未追蹤私人帳號，無法存取其限時動態
- **CDN URL 時效性**：Instagram CDN URL 附有時效簽名，解析後須立即下載，否則連結可能失效
- **封存 API 依賴 Playwright**：Instagram 對直接 HTTP 請求有 bot 偵測，封存功能必須啟動 headless 瀏覽器，初次載入較慢
- **無持久化**：每次應用重啟後，解析結果不會保留
