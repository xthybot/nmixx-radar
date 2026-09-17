# NMIXX Radar Public Release Design

## Purpose

Turn the existing NMIXX information site into a standalone public repository that small deployments can run with `uv`, systemd, and Nginx. The installation must protect member access without removing the existing RSS and AI update workflow.

## Deployment boundary

Nginx terminates TLS for the public domain on port 443 and proxies requests to `127.0.0.1:32765`. Uvicorn also binds to `0.0.0.0:32765` so trusted local-network users can retain direct access.

Direct HTTP access is deliberately limited: only requests whose peer address is loopback or a private IP range may create or use the separate LAN session cookie. Public peers on the raw port receive no authenticated session. HTTPS uses a distinct `Secure`, `HttpOnly`, `SameSite=Lax` cookie. Privileged routes always require HTTPS, regardless of peer address.

## Identity and sessions

SQLite is used only for security-sensitive, concurrent data: users, invitations, sessions, push subscriptions, and rate-limit records. The database is stored below the configured runtime data directory and is never committed.

The first startup creates the configured bootstrap administrator only when no administrator exists. Invitations are one-time, expire after a configured period, and are stored as hashes. Passwords use Argon2. Sessions have a 30-day idle lifetime and 180-day absolute lifetime. A session nearing its absolute lifetime (14 days remaining) exposes a renewal-required flag; submitting the current password rotates the session and starts a new absolute lifetime. Expired sessions are rejected on the next protected request without deleting push subscriptions.

## Content and update pipeline

Static editorial content remains in `site_data.py`. Generated update and hero records remain file-backed JSON/Python-compatible data rather than moving the existing content pipeline into SQLite. Generation uses a process lock and write-to-temporary-then-replace semantics. Loaders cache parsed records by modification time and do not reload Python modules on every request. Generated records have finite retention.

JYP, official YouTube, and Google News feeds remain supported. Each source is labeled as either official or RSS news in the UI. Scraped text and model responses are untrusted. Accepted links must be HTTPS and pass a source-specific host allowlist. AI command invocation uses an explicit executable and argument list, never `shell=True`.

## Push and image proxy

Push subscriptions belong to the logged-in user that created them. Subscription payloads are strictly validated, bounded, and rate limited. General users may create, inspect, or delete only their own subscription. Test delivery is HTTPS administrator-only. VAPID and subscription files are replaced by secured runtime-data storage with directory mode `0700` and files mode `0600`.

The image proxy only fetches HTTPS URLs from approved hosts, disables redirects, caps response bytes and decoded pixels, uses a bounded cache, and runs blocking image work outside the async event loop.

## Runtime configuration and operations

`.sample.env` is committed with safe defaults including `APP_HOST=0.0.0.0` and `APP_PORT=32765`; `.env` is ignored. Nginx, systemd site service, update service/timer, and hero service/timer are committed as templates. The README documents configuration, bootstrap, backups, recovery, Nginx TLS, raw LAN limitations, and upgrades.

## Repository policy

The project is an independent repository named `xthybot/nmixx-radar`. It contains no workspace references, private network addresses, generated user data, VAPID material, cache, OpenClaw dependency, or tmux operational requirement. It includes MIT licensing, contribution and security policy documents, and a non-official NMIXX/JYP content and trademark notice.

## Acceptance criteria

1. A fresh runtime directory can initialize the administrator, log in through HTTPS, create an invitation, register a member, and renew a near-expiry session.
2. A private-LAN HTTP peer can receive only the LAN session; a public peer cannot authenticate on the raw port; HTTPS-only administrative actions reject LAN HTTP.
3. Update, image, and push endpoints enforce their stated URL, ownership, size, and access restrictions.
4. The full test suite, static checks, lockfile validation, and dependency vulnerability scan pass.
5. A clean checkout can follow the documented `uv`, systemd, and Nginx process without any machine-specific paths or services.
