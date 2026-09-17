# NMIXX Radar

NMIXX Radar 是一個非官方、以手機優先設計的 NMIXX 情報站，使用 FastAPI 建置，集中呈現公告、影片、行程、作品、成員資訊與精選 RSS 新聞。支援安裝為 PWA、瀏覽器 Push 通知，以及選用的 AI 更新審核。

本 repository 僅提供軟體。NMIXX、JYP Entertainment、藝人名稱、商標、標誌及來源素材均屬其各自權利人所有。站台管理者須自行遵守來源網站條款、著作權、隱私與當地法律。RSS 新聞會與官方來源明確區隔，不得視為已驗證的官方資訊。

## 功能

- 管理者建立一次性邀請碼的成員制登入。
- 長效 session：30 天閒置期限、180 天絕對期限，以及提前重新驗證提醒。
- JYP 與 YouTube 官方來源，另可選用 Google News RSS 與 AI 審核。
- 已登入成員可使用 PWA 與 Web Push 通知。
- Nginx HTTPS 正式部署，同時保留 32765 埠的區網直連能力。
- 網站、更新監看與 Hero 圖片更新各有 systemd service 與 timer。

## 快速開始

需求：Python 3.12 以上，以及 [uv](https://docs.astral.sh/uv/)。

```bash
git clone https://github.com/xthybot/nmixx-radar.git
cd nmixx-radar
cp .sample.env .env
chmod 600 .env
# 編輯 .env：設定 PUBLIC_BASE_URL 與高強度 BOOTSTRAP_ADMIN_PASSWORD。
bash install.sh
uv run uvicorn app.main:app --host 0.0.0.0 --port 32765
```

要供公開瀏覽器、PWA 與 Push 使用時，請以有效的 HTTPS 憑證設定內附的 Nginx 範例。完整步驟見[部署文件](docs/DEPLOYMENT.md)。

## 執行期資料

所有可變動資料都放在 `DATA_DIR`（預設為 `./data`）下，且會被 Git 忽略：

- 帳號、邀請碼、session 與 Push 訂閱資料庫。
- VAPID 金鑰資料。
- 產生的更新與 Hero 圖片記錄。
- 爬蟲狀態與圖片快取。

絕不可提交 `.env` 或執行期資料。

## 開發檢查

```bash
uv sync --frozen
uv run python -m compileall -q app
uv run python -m unittest discover -s tests -v
uvx ruff check .
uv lock --check
uvx pip-audit --local
```

## 安全模型

公開流量必須走 Nginx 的 HTTPS 443 埠。應用程式原始埠仍可供本機或私人網路使用，但直接 HTTP 有刻意限制：公網使用者無法登入，管理與 Push 管理操作則一律要求 HTTPS。公開部署前請閱讀 [SECURITY.md](SECURITY.md)。

## 授權

原始碼採用 [MIT License](LICENSE) 授權。
