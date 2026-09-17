# Deployment

This guide uses `/opt/nmixx-radar` and a dedicated Linux account named `nmixx-radar`. Replace the domain and paths if your installation differs.

## 1. Install and initialize

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

Set a unique `BOOTSTRAP_ADMIN_PASSWORD` and the real `PUBLIC_BASE_URL` before the first service start. The bootstrap account is created only when no administrator exists; remove the bootstrap password from `.env` after verifying the first administrator can log in.

## 2. systemd

The included units intentionally use a non-root account, private temporary files, and a writable exception only for `/opt/nmixx-radar/data`. They assume uv is at `/home/nmixx-radar/.local/bin/uv`; adjust the `PATH` lines if your uv installation differs.

```bash
sudo cp /opt/nmixx-radar/deploy/systemd/*.service /opt/nmixx-radar/deploy/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now nmixx-radar.service nmixx-radar-update.timer nmixx-radar-hero.timer
sudo systemctl status nmixx-radar.service
systemctl list-timers 'nmixx-radar-*'
```

The two timers wake every minute but each job checks `UPDATE_INTERVAL_SECONDS` or `HERO_UPDATE_INTERVAL_SECONDS` in `.env` before fetching anything. This lets an operator change timing without editing systemd units.

## 3. Nginx and HTTPS

Copy `deploy/nginx/nmixx-radar.conf` to your Nginx site directory, replace `radar.example.com` and certificate paths, then test and reload it:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Nginx accepts public traffic on HTTPS port 443 and proxies it to `127.0.0.1:32765`. `TRUSTED_PROXY_IPS` must keep `127.0.0.1,::1` unless you deliberately place another trusted proxy in front of the app.

The application still binds `0.0.0.0:32765` for local/LAN use. Protect that port with your host firewall so the public Internet cannot reach it. Only private-IP HTTP clients can log in; HTTP remains weaker than HTTPS. Administration, invitations, password resets, session renewal, and Push subscription management require HTTPS regardless of peer address.

## 4. Normal operation and updates

```bash
sudo -u nmixx-radar -H bash -lc 'cd /opt/nmixx-radar && uv run --frozen python -m app.update_watcher --once'
sudo -u nmixx-radar -H bash -lc 'cd /opt/nmixx-radar && uv run --frozen python -m app.hero_image_watcher --once'

sudo -u nmixx-radar -H git -C /opt/nmixx-radar pull --ff-only
sudo -u nmixx-radar -H bash -lc 'cd /opt/nmixx-radar && uv sync --frozen'
sudo systemctl restart nmixx-radar.service
```

AI review is optional. Configure only one of local Ollama, `AI_REVIEW_COMMAND`, or OpenAI credentials. Treat all RSS and AI-generated text as untrusted input; the application only retains allowed HTTPS source domains.

## 5. Backup and restore

Backups include SQLite through SQLite's backup API, generated JSON, VAPID material, and subscriptions. Store archives outside the server and protect them like passwords.

```bash
sudo -u nmixx-radar -H bash -lc 'cd /opt/nmixx-radar && uv run --frozen python -m scripts.backup_runtime --output-dir /var/backups/nmixx-radar'
```

To restore, stop every application job first. The restore command moves the current `DATA_DIR` aside instead of deleting it, then requires an explicit acknowledgement.

```bash
sudo systemctl stop nmixx-radar.service nmixx-radar-update.timer nmixx-radar-hero.timer
sudo -u nmixx-radar -H bash -lc 'cd /opt/nmixx-radar && uv run --frozen python -m scripts.restore_runtime /var/backups/nmixx-radar/nmixx-radar-YYYYMMDDTHHMMSSZ.tar.gz --yes-replace-data'
sudo systemctl start nmixx-radar.service nmixx-radar-update.timer nmixx-radar-hero.timer
```

## 6. Verification

```bash
cd /opt/nmixx-radar
uv run python -m unittest discover -s tests -v
uvx ruff check .
uv lock --check
uvx pip-audit --local
sudo systemd-analyze verify /etc/systemd/system/nmixx-radar*.service /etc/systemd/system/nmixx-radar*.timer
sudo nginx -t
```
