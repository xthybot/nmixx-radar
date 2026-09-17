# NMIXX Radar

NMIXX Radar is an unofficial, mobile-first FastAPI information hub for NMIXX notices, videos, schedules, releases, member information, and selected RSS news. It supports PWA installation, browser Push notifications, and optional AI-assisted update review.

This repository contains software only. NMIXX, JYP Entertainment, artist names, logos, and source material belong to their respective owners. Site operators are responsible for complying with source-site terms, copyright, privacy, and local law. RSS news is labeled separately from official sources and must not be treated as verified official information.

## Features

- Invitation-only member access with an administrator bootstrap account.
- Long-lived sessions: 30 days of inactivity, 180-day absolute lifetime, and an advance renewal warning.
- Official JYP and YouTube sources plus optional Google News RSS and AI review.
- PWA and Web Push notifications for authenticated members.
- Nginx HTTPS deployment with retained direct LAN access on port 32765.
- systemd services and timers for the site, update watcher, and hero image refresh.

## Quick start

Requirements: Python 3.12 or newer and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/xthybot/nmixx-radar.git
cd nmixx-radar
cp .sample.env .env
chmod 600 .env
# Edit .env: set PUBLIC_BASE_URL and a strong BOOTSTRAP_ADMIN_PASSWORD.
bash install.sh
uv run uvicorn app.main:app --host 0.0.0.0 --port 32765
```

For public browser, PWA, and Push use, configure the included Nginx template with a valid HTTPS certificate. See [deployment documentation](docs/DEPLOYMENT.md).

## Runtime data

All mutable data belongs under `DATA_DIR` (default `./data`) and is ignored by Git:

- Account, invitation, session, and Push subscription database.
- VAPID key material.
- Generated update and hero records.
- Crawler state and image cache.

Never commit `.env` or runtime data.

## Development checks

```bash
uv sync --frozen
uv run python -m compileall -q app
uv run python -m unittest discover -s tests -v
uvx ruff check .
uv lock --check
uvx pip-audit --local
```

## Security model

Public traffic must use Nginx HTTPS on port 443. The raw application port stays available for local or private-network use, but direct HTTP is intentionally restricted: public peers cannot log in, and administrative or Push-management actions require HTTPS. Review [SECURITY.md](SECURITY.md) before operating a public instance.

## License

The source code is available under the [MIT License](LICENSE).
