# 部署說明

本文件以 `/opt/nmixx-radar` 與專用 Linux 帳號 `nmixx-radar` 為例。若實際環境不同，請替換網域與路徑。

## 1. 安裝與初始化

```bash
sudo useradd --system --create-home --home-dir /home/nmixx-radar --shell /usr/sbin/nologin nmixx-radar
sudo git clone https://github.com/xthybot/nmixx-radar.git /opt/nmixx-radar
sudo chown -R nmixx-radar:nmixx-radar /opt/nmixx-radar
sudo -u nmixx-radar -H bash -lc 'curl -LsSf https://astral.sh/uv/install.sh | sh'
sudo -u nmixx-radar -H bash -lc 'cd /opt/nmixx-radar && uv sync --frozen'
sudo -u nmixx-radar cp /opt/nmixx-radar/.sample.env /opt/nmixx-radar/.env
sudo -u nmixx-radar chmod 600 /opt/nmixx-radar/.env
sudo -u nmixx-radar editor /opt/nmixx-radar/.env
```

第一次啟動服務前，請設定唯一且高強度的 `BOOTSTRAP_ADMIN_PASSWORD` 與正確的 `PUBLIC_BASE_URL`。只有系統內尚無任何管理者時，才會建立 bootstrap 管理者；確認第一位管理者可以登入後，請從 `.env` 移除 bootstrap 密碼。

## 2. systemd

內附 unit 會以非 root 帳號運作、使用私有暫存目錄，且只允許寫入 `/opt/nmixx-radar/data`。範例假設 uv 位於 `/home/nmixx-radar/.local/bin/uv`；若 uv 安裝位置不同，請調整 unit 中的 `PATH` 行。

```bash
sudo cp /opt/nmixx-radar/deploy/systemd/*.service /opt/nmixx-radar/deploy/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now nmixx-radar.service nmixx-radar-update.timer nmixx-radar-hero.timer
sudo systemctl status nmixx-radar.service
systemctl list-timers 'nmixx-radar-*'
```

兩個 timer 每分鐘喚醒一次，但各工作會先依 `.env` 的 `UPDATE_INTERVAL_SECONDS` 或 `HERO_UPDATE_INTERVAL_SECONDS` 判斷是否已到執行時間，未到時間不會抓取資料。因此調整更新頻率時不必修改 systemd unit。

## 3. Nginx 與 HTTPS

將 `deploy/nginx/nmixx-radar.conf` 複製到 Nginx 的站台設定目錄，替換 `radar.example.com` 與憑證路徑後，測試並重新載入：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Nginx 會在 HTTPS 443 埠接收公開流量，並代理到 `127.0.0.1:32765`。除非刻意在前方加入另一個受信任的 proxy，否則 `TRUSTED_PROXY_IPS` 應保留 `127.0.0.1,::1`。

應用程式仍依 `.env` 預設綁定 `0.0.0.0:32765` 以供本機／區網使用。請使用主機防火牆保護此埠，避免公網能直接連線。只有私有 IP 的 HTTP 用戶端可登入，HTTP 的安全性仍低於 HTTPS。無論來源 IP 為何，管理、邀請碼、密碼重設、session 續期與 Push 訂閱管理都要求 HTTPS。

## 4. 日常操作與更新

```bash
sudo -u nmixx-radar -H bash -lc 'cd /opt/nmixx-radar && uv run --frozen python -m app.update_watcher --once'
sudo -u nmixx-radar -H bash -lc 'cd /opt/nmixx-radar && uv run --frozen python -m app.hero_image_watcher --once'

sudo -u nmixx-radar -H git -C /opt/nmixx-radar pull --ff-only
sudo -u nmixx-radar -H bash -lc 'cd /opt/nmixx-radar && uv sync --frozen'
sudo systemctl restart nmixx-radar.service
```

AI 審核為選用功能。只設定本機 Ollama、`AI_REVIEW_COMMAND` 或 OpenAI 憑證中的其中一種方式即可。RSS 與 AI 產生文字都必須視為不可信輸入；應用程式只會保留來自允許 HTTPS 網域的連結。

## 5. 備份與還原

備份會透過 SQLite backup API 包含 SQLite 資料庫、產生的 JSON、VAPID 資料與訂閱資料。請將備份檔存放於伺服器外部，並以與密碼相同的標準保護。

```bash
sudo -u nmixx-radar -H bash -lc 'cd /opt/nmixx-radar && uv run --frozen python -m scripts.backup_runtime --output-dir /var/backups/nmixx-radar'
```

還原前必須先停止所有應用程式工作。還原命令不會直接刪除既有 `DATA_DIR`，而是先將它移至保留位置，並要求明確確認參數。

```bash
sudo systemctl stop nmixx-radar.service nmixx-radar-update.timer nmixx-radar-hero.timer
sudo -u nmixx-radar -H bash -lc 'cd /opt/nmixx-radar && uv run --frozen python -m scripts.restore_runtime /var/backups/nmixx-radar/nmixx-radar-YYYYMMDDTHHMMSSZ.tar.gz --yes-replace-data'
sudo systemctl start nmixx-radar.service nmixx-radar-update.timer nmixx-radar-hero.timer
```

## 6. 驗證

```bash
cd /opt/nmixx-radar
uv run python -m unittest discover -s tests -v
uvx ruff check .
uv lock --check
uvx pip-audit --local
sudo systemd-analyze verify /etc/systemd/system/nmixx-radar*.service /etc/systemd/system/nmixx-radar*.timer
sudo nginx -t
```
