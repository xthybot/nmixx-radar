# NMIXX Radar 維護交接指南

本文件提供 Codex、Claude、OpenClaw、Hermes 或其他自動化 agent 維護本專案時使用。開始任何工作前，先閱讀本文件與目前的 `README.md`、`docs/DEPLOYMENT.md`、`.sample.env`，並以工作目錄中的實際程式碼與 Git 狀態為準。

## 1. 系統定位與不可改變的原則

NMIXX Radar 是非官方、邀請制的 NMIXX 情報站。它不提供公開註冊、電子郵件帳號流程或第三方身分登入。

- 正式公開流量：Nginx 在 HTTPS 443 埠終結 TLS，代理到 `127.0.0.1:32765`。
- 應用程式預設仍綁定 `0.0.0.0:32765`，供本機與區網使用；主機防火牆必須禁止公網直接連入這個埠。
- 只有私有 IP 的區網 HTTP 用戶端可登入，且使用獨立的非 Secure session cookie。
- 邀請碼註冊、管理後台、停用帳號、重設密碼、撤銷 session、session 續期與 Push 管理一律要求 HTTPS。
- HTTPS session 採 30 天閒置期限、180 天絕對期限；剩 14 天時提醒使用者重新驗證密碼。重新驗證會建立新的 session，不能直接延長舊 token。
- Push 訂閱屬於帳號資料，不因 session 到期而刪除。
- 本專案的公開性與安全邊界優先於為了方便而新增的功能。若修改可能改變上述行為，先向使用者說明影響並取得同意。

## 2. 架構與資料位置

| 元件 | 位置 | 責任 |
| --- | --- | --- |
| 網站與路由 | `app/main.py` | FastAPI app、登入流程、權限檢查、HTTP 回應安全標頭。 |
| 認證 | `app/auth.py` | Argon2 密碼、邀請碼、session、帳號狀態與密碼重設。 |
| 資料庫 | `app/database.py` | SQLite schema 與私有檔案權限。 |
| Push | `app/push.py` | VAPID、訂閱 schema、帳號綁定、數量限制與傳送。 |
| 更新監看 | `app/update_watcher.py` | JYP／YouTube／Google News RSS、AI 或規則審核、推播。 |
| Hero 圖片監看 | `app/hero_image_watcher.py` | 從 JYP Gallery 更新首頁輪播圖片。 |
| 執行期 JSON | `app/runtime_data.py` | 原子寫入、檔案鎖、更新筆數上限。 |
| 圖片代理 | `app/image_proxy.py` | 白名單、禁止轉址、下載／像素／快取上限、非同步下載。 |
| 外部連結政策 | `app/url_policy.py` | 只允許 HTTPS 與明確網域白名單。 |
| 靜態資料／模板 | `app/site_data.py`、`app/templates/`、`app/static/` | 首頁內容、PWA 與使用者介面。 |

所有可變動資料都只能位於 `DATA_DIR`（預設 `./data`），包含：

- `radar.sqlite3`、SQLite WAL/SHM 檔案。
- `vapid_private.pem`。
- `generated_updates.json`、`generated_hero_slides.json`、更新狀態、Hero 狀態與圖片快取。

`data/`、`.env`、金鑰、訂閱資料、快取與任何個資不得加入 Git。不要重新引入將爬蟲結果寫回 Python 模組、每次請求 `importlib.reload()`，或舊的 `.push_state`／`.update_state` 目錄。

## 3. 設定與背景工作

複製 `.sample.env` 為 `.env` 後再設定。不得將真實 `.env` 內容貼到聊天、日誌、Issue、commit 或測試輸出。

- 首次啟動前必須替換 `BOOTSTRAP_ADMIN_PASSWORD`；第一個管理者建立後，建議自 `.env` 移除 bootstrap 密碼。
- `APP_HOST`、`APP_PORT`、`UPDATE_INTERVAL_SECONDS`、`HERO_UPDATE_INTERVAL_SECONDS` 都由 `.env` 控制。
- `OLLAMA_MODEL` 有值時，更新器會直接呼叫 `OLLAMA_HOST/api/generate`；這不是 OpenClaw cron。
- 若不使用 Ollama，可設定 `AI_REVIEW_COMMAND` 或 `OPENAI_API_KEY` 加 `OPENAI_MODEL`，但三者只選一種。
- `AI_REVIEW_COMMAND` 以參數陣列執行，不得改回 `shell=True`，也不得在設定值中依賴 pipe、重導向或 shell 語法。

正式 systemd unit 位於 `deploy/systemd/`：

```bash
sudo systemctl status nmixx-radar.service
systemctl list-timers 'nmixx-radar-*'
journalctl -u nmixx-radar.service -f
journalctl -u nmixx-radar-update.service -n 100 --no-pager
journalctl -u nmixx-radar-hero.service -n 100 --no-pager
```

Timer 每分鐘被喚醒一次，但 Python 工作會依 `.env` 的間隔自行略過未到期的執行。不要用 cron、tmux、OpenClaw heartbeat 或其他私人環境依賴取代 systemd。

## 4. 安全維護規則

任何 agent 都不得為了快速完成工作而降低以下限制：

1. 密碼必須保持 Argon2 雜湊；不得記錄或回傳密碼。
2. session token 只能儲存雜湊；HTTPS cookie 必須維持 `HttpOnly`、`Secure`、`SameSite=Lax`。
3. 不得信任未受信任客戶端傳來的 `X-Forwarded-*` 標頭；只有 `TRUSTED_PROXY_IPS` 的來源可宣告 HTTPS。
4. Push endpoint 必須綁定目前登入帳號、驗證資料格式與大小、限制每帳號訂閱數並限流；測試推播維持 HTTPS 管理者專用。
5. 所有外部連結只允許 `app/url_policy.py` 定義的 HTTPS 網域；AI、RSS、HTML 與圖片資料都視為不可信輸入。
6. 圖片代理必須維持來源白名單、禁止 HTTP 與重新導向、限制下載大小和像素數，並避免在 FastAPI 事件迴圈中做同步網路 I/O。
7. `DATA_DIR` 應為 `0700`，資料庫與 VAPID 私鑰應為 `0600`。不要放寬這些權限。
8. 不得提交、顯示或掃描後外洩 `.env`、SQLite、VAPID 私鑰、Push endpoint、session cookie 或使用者資料。

Google News 是第三方新聞 RSS，不是官方公告。任何新增或修改的介面都必須保留這個區別。AI 審核僅決定候選內容是否收錄，不能被視為事實查核。

## 5. 正常修改流程

1. 先執行 `git status --short`，保留使用者既有的未提交變更；不要使用 `git reset --hard`、`git checkout --` 或廣泛刪除指令。
2. 先閱讀受影響模組與其測試。新增功能或修正 bug 時，先新增會失敗的測試，再寫實作。
3. 變更保持小而聚焦。資料庫 schema、網路策略、登入流程、Push 或外部網路存取屬高風險修改，必須說明安全影響。
4. 修改完成後，至少執行與變更相符的測試；準備提交或推送前執行完整驗證。
5. 文件、`.sample.env`、systemd unit 與 Nginx 範例若受功能影響，必須同步更新。

完整驗證命令：

```bash
uv sync --frozen
uv run python -m compileall -q app scripts
uv run python -m unittest discover -s tests -v
uvx ruff check .
uvx pyright
uv lock --check
uvx pip-audit --local
systemd-analyze verify deploy/systemd/*.service deploy/systemd/*.timer
git diff --check
```

若環境有 Nginx，另外執行 `sudo nginx -t`。修改部署流程後，應以全新 `DATA_DIR` 驗證啟動、管理者登入、邀請註冊、更新器與 Hero 更新器。

## 6. 備份、還原與可逆操作

備份與還原是高風險操作。還原前必須先停止網站與兩個 timer，確認備份檔目標，並使用文件要求的 `--yes-replace-data` 明確確認參數。還原程式會將舊資料目錄改名保留；不要改成直接刪除。

```bash
uv run --frozen python -m scripts.backup_runtime --output-dir /安全的備份目錄
uv run --frozen python -m scripts.restore_runtime /備份檔.tar.gz --yes-replace-data
```

執行前後遵循 `docs/DEPLOYMENT.md` 的停啟服務順序。備份檔含帳號、session、訂閱與私鑰，必須視同機密資料處理。

## 7. Git 與公開 repository

- 所有公開內容使用繁體中文文件；MIT `LICENSE` 保留原始英文法律文字。
- 提交前檢查 `git diff --check`、`git status --short`，並搜尋是否誤放私密資料。
- 未取得使用者明確授權前，不建立公開 repo、不 push、不發 Issue、不建立 PR，也不對外傳送訊息。
- 已明確要求推送時，先完成完整驗證，再以清楚、單一目的的 commit 推送至 `main`。
- 不要加入私人絕對路徑、內網 IP、私人模型名稱、OpenClaw、tmux 或舊 Next.js 相容層。

完成工作時，回報變更檔案、驗證結果、是否已推送，以及仍存在的操作風險。不要把「程式能啟動」當成完成證據。
