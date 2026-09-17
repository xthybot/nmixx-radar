# NMIXX Radar Public Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a secure, standalone, publicly shareable NMIXX Radar deployment with invited user access, retained RSS/AI updates, and systemd/Nginx operations.

**Architecture:** Keep editorial and crawler content file-backed, but store concurrent identity, session, invitation, and Push data in a single local SQLite database. FastAPI enforces HTTPS and role boundaries at route dependencies; two cookie lanes separate TLS browser sessions from explicitly permitted private-LAN HTTP sessions.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, SQLite (`sqlite3`), Argon2, Uvicorn, systemd, Nginx, unittest, Ruff, pip-audit.

**Spec:** `docs/superpowers/specs/2026-09-17-public-release-design.md`

## Global Constraints

- Commit `.sample.env`, never `.env`, runtime databases, caches, subscriptions, VAPID keys, or crawler state.
- Use `APP_HOST=0.0.0.0` and `APP_PORT=32765` as `.sample.env` defaults.
- Treat RSS and AI output as untrusted: accept only HTTPS links that match the configured source policy.
- Permit raw HTTP sessions only for private or loopback peer addresses; reject administrative actions unless the request is HTTPS.
- Use TDD: every production behavior starts with a failing unittest that is observed before implementation.
- Keep public dependencies portable; do not require OpenClaw, tmux, private addresses, or the legacy Next.js project.

---

### Task 1: Establish the standalone public repository baseline

**Files:**
- Create: `.sample.env`, `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`, `docs/DEPLOYMENT.md`
- Modify: `.gitignore`, `README.md`, `pyproject.toml`, `install.sh`
- Test: `tests/test_repository_hygiene.py`

**Interfaces:**
- Produces: documented runtime variables and a repository-safe ignored-file policy used by all later tasks.

- [ ] **Step 1: Write failing repository hygiene tests**

```python
def test_sample_environment_has_no_secret_values():
    content = Path(".sample.env").read_text(encoding="utf-8")
    assert "BOOTSTRAP_ADMIN_PASSWORD=change-me" in content
    assert "sk-" not in content

def test_private_runtime_paths_are_ignored():
    ignored = Path(".gitignore").read_text(encoding="utf-8")
    for path in (".env", "data/", ".push_state/", ".update_state/", ".image_cache/"):
        assert path in ignored
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run python -m unittest tests.test_repository_hygiene -v`

Expected: FAIL because `.sample.env` and the hygiene test implementation are absent.

- [ ] **Step 3: Add portable configuration and repository policy documents**

Create `.sample.env` with documented defaults, add MIT licensing and the non-official content notice, remove all private paths/IPs/OpenClaw/tmux instructions from README, and make `install.sh` run `uv sync --frozen`.

- [ ] **Step 4: Run the focused test and project baseline**

Run: `uv run python -m unittest tests.test_repository_hygiene -v && uv lock --check`

Expected: PASS and lockfile check succeeds.

- [ ] **Step 5: Commit the baseline**

```bash
git add .gitignore .sample.env LICENSE SECURITY.md CONTRIBUTING.md README.md docs/DEPLOYMENT.md pyproject.toml install.sh tests/test_repository_hygiene.py
git commit -m "chore: establish public repository baseline"
```

### Task 2: Add configuration, runtime directories, and SQLite security store

**Files:**
- Create: `app/config.py`, `app/database.py`, `app/security.py`
- Modify: `app/__init__.py`, `pyproject.toml`
- Test: `tests/test_config.py`, `tests/test_database.py`

**Interfaces:**
- Produces: `Settings.from_env() -> Settings`, `Database(settings).initialize() -> None`, and secure runtime directory creation.
- Consumes: variables documented in `.sample.env`.

- [ ] **Step 1: Write failing tests for isolated settings and database initialization**

```python
class ConfigTests(unittest.TestCase):
    def test_settings_use_explicit_runtime_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory) / "runtime"
            with patch.dict(os.environ, {"DATA_DIR": str(data_dir)}, clear=False):
                self.assertEqual(Settings.from_env().data_dir, data_dir)

    def test_database_creates_schema_and_private_runtime_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings.for_test(Path(directory) / "runtime")
            Database(settings).initialize()
            self.assertTrue((settings.data_dir / "radar.sqlite3").exists())
```

- [ ] **Step 2: Verify the tests fail**

Run: `uv run python -m unittest tests.test_config tests.test_database -v`

Expected: FAIL because settings and database modules do not exist.

- [ ] **Step 3: Implement settings and migration-free schema initialization**

Create tables for `users`, `invitations`, `sessions`, `push_subscriptions`, and `rate_limit_events`; use foreign keys, WAL mode, parameterized statements, and explicit file permissions.

- [ ] **Step 4: Verify focused tests pass**

Run: `uv run python -m unittest tests.test_config tests.test_database -v`

Expected: PASS.

- [ ] **Step 5: Commit the runtime store**

```bash
git add app/config.py app/database.py app/security.py app/__init__.py pyproject.toml tests/test_config.py tests/test_database.py
git commit -m "feat: add secure runtime configuration and database"
```

### Task 3: Implement invitation-only authentication and session renewal

**Files:**
- Create: `app/auth.py`, `app/templates/login.html`, `app/templates/register.html`, `app/templates/account.html`
- Modify: `app/main.py`, `app/templates/index.html`, `app/static/app.js`, `app/static/styles.css`
- Test: `tests/test_auth.py`, `tests/test_sessions.py`

**Interfaces:**
- Consumes: `Database`, `Settings`.
- Produces: `AuthService.bootstrap_admin()`, `create_invitation()`, `register()`, `authenticate()`, `renew_session()`, and `current_user()` route dependency.

- [ ] **Step 1: Write failing auth tests**

```python
def test_bootstrap_admin_is_created_only_once(client, settings):
    initialize_application(settings)
    assert login(client, settings.bootstrap_admin_username, settings.bootstrap_admin_password).status_code == 302

def test_invitation_can_be_used_once(client, admin_session):
    code = create_invitation(client, admin_session)
    assert register(client, code, "member", "long-password").status_code == 302
    assert register(client, code, "other", "long-password").status_code == 400
```

- [ ] **Step 2: Verify expected auth failures**

Run: `uv run python -m unittest tests.test_auth tests.test_sessions -v`

Expected: FAIL because authenticated routes and service functions do not exist.

- [ ] **Step 3: Implement Argon2 users, invitations, hashed opaque sessions, and renewal UI**

Implement a 30-day idle expiration, 180-day absolute expiration, 14-day renewal flag, password re-authentication, session rotation, logout, administrator revocation, and account status messaging.

- [ ] **Step 4: Verify session behavior**

Run: `uv run python -m unittest tests.test_auth tests.test_sessions -v`

Expected: PASS, including an expired session receiving a login redirect and a renewed session receiving a new absolute expiration.

- [ ] **Step 5: Commit authentication**

```bash
git add app/auth.py app/main.py app/templates app/static/app.js app/static/styles.css tests/test_auth.py tests/test_sessions.py
git commit -m "feat: add invitation-only authentication"
```

### Task 4: Enforce HTTPS, LAN session, and administrator boundaries

**Files:**
- Create: `app/access.py`
- Modify: `app/main.py`, `app/auth.py`
- Test: `tests/test_access.py`

**Interfaces:**
- Produces: `request_transport(request) -> Literal["https", "lan_http", "public_http"]`, `require_authenticated_user`, and `require_https_admin`.

- [ ] **Step 1: Write failing transport-policy tests**

```python
def test_public_http_peer_cannot_create_authenticated_session(client):
    response = client.post("/login", headers={"X-Test-Peer-IP": "198.51.100.9"}, data=valid_credentials)
    assert response.status_code == 403

def test_private_http_peer_receives_lan_cookie(client):
    response = client.post("/login", headers={"X-Test-Peer-IP": "192.168.1.10"}, data=valid_credentials)
    assert "radar_lan_session" in response.headers["set-cookie"]

def test_lan_administrator_request_is_rejected(client, lan_admin_session):
    assert client.post("/admin/invitations", headers={"X-Test-Peer-IP": "192.168.1.10"}).status_code == 403
```

- [ ] **Step 2: Verify expected failures**

Run: `uv run python -m unittest tests.test_access -v`

Expected: FAIL because transport policy does not exist.

- [ ] **Step 3: Implement peer classification and two session cookie lanes**

Trust `X-Forwarded-Proto` only from configured trusted proxy addresses. Classify private RFC1918, loopback, and link-local clients with `ipaddress`; deny raw public HTTP login; issue `Secure` HTTPS cookies and non-Secure LAN cookies with different names; gate all privileged routes on HTTPS and administrator role.

- [ ] **Step 4: Verify all access cases**

Run: `uv run python -m unittest tests.test_access -v`

Expected: PASS.

- [ ] **Step 5: Commit access control**

```bash
git add app/access.py app/auth.py app/main.py tests/test_access.py
git commit -m "feat: enforce HTTPS and LAN access boundaries"
```

### Task 5: Secure generated content and crawler behavior

**Files:**
- Create: `app/generated_store.py`
- Modify: `app/site_data.py`, `app/update_watcher.py`, `app/hero_image_watcher.py`, `app/update_sources.json`
- Test: `tests/test_generated_store.py`, `tests/test_update_watcher.py`, `tests/test_hero_watcher.py`

**Interfaces:**
- Produces: `GeneratedStore.read_updates()`, `write_updates(items)`, `read_hero_slides()`, and `validate_external_url(url, allowed_hosts)`.

- [ ] **Step 1: Write failing safety tests**

```python
class GeneratedStoreTests(unittest.TestCase):
    def test_generated_updates_reject_javascript_url(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                GeneratedStore(Path(directory)).write_updates([{"href": "javascript:alert(1)"}])

    def test_generated_store_keeps_only_configured_retention(self):
        with tempfile.TemporaryDirectory() as directory:
            store = GeneratedStore(Path(directory), max_updates=50)
            store.write_updates(make_updates(60))
            self.assertEqual(len(store.read_updates()), 50)
```

- [ ] **Step 2: Verify the tests fail**

Run: `uv run python -m unittest tests.test_generated_store tests.test_update_watcher tests.test_hero_watcher -v`

Expected: FAIL because the store and URL policy do not exist.

- [ ] **Step 3: Implement locked atomic JSON generation and safe source policies**

Use a lock file, temp file, `os.replace`, bounded source reads, explicit timeout, HTTPS-only URL validation, source labels (`官方` or `新聞 RSS`), and a command adapter that calls `subprocess.run([settings.ai_review_command], input=payload, text=True, capture_output=True, timeout=settings.ai_review_timeout_seconds, check=False, shell=False)`.

- [ ] **Step 4: Verify crawler tests pass**

Run: `uv run python -m unittest tests.test_generated_store tests.test_update_watcher tests.test_hero_watcher -v`

Expected: PASS.

- [ ] **Step 5: Commit content hardening**

```bash
git add app/generated_store.py app/site_data.py app/update_watcher.py app/hero_image_watcher.py app/update_sources.json tests/test_generated_store.py tests/test_update_watcher.py tests/test_hero_watcher.py
git commit -m "feat: harden generated content pipeline"
```

### Task 6: Bind Push subscriptions to authenticated users

**Files:**
- Modify: `app/push.py`, `app/main.py`, `app/static/app.js`
- Test: `tests/test_push.py`

**Interfaces:**
- Consumes: `Database`, `current_user`, `require_https_admin`.
- Produces: user-scoped subscribe/unsubscribe endpoints and administrator-only push testing.

- [ ] **Step 1: Write failing Push ownership and rate-limit tests**

```python
def test_member_cannot_remove_another_members_subscription(client, two_members):
    first, second = two_members
    subscribe(client, first)
    assert unsubscribe(client, second).status_code == 404

def test_push_test_requires_https_administrator(client, lan_admin_session):
    assert client.post("/api/push/test", headers={"X-Test-Peer-IP": "192.168.1.10"}).status_code == 403
```

- [ ] **Step 2: Verify expected failures**

Run: `uv run python -m unittest tests.test_push -v`

Expected: FAIL because subscriptions are globally readable and test Push is public.

- [ ] **Step 3: Implement schema validation, ownership, quotas, and secured VAPID storage**

Validate endpoint and key fields, cap payload size and subscriptions per user, persist VAPID data in the runtime directory with `0700`/`0600` permissions, and remove automatic browser calls to the test-push endpoint.

- [ ] **Step 4: Verify Push tests pass**

Run: `uv run python -m unittest tests.test_push -v`

Expected: PASS.

- [ ] **Step 5: Commit Push hardening**

```bash
git add app/push.py app/main.py app/static/app.js tests/test_push.py
git commit -m "feat: secure per-user push subscriptions"
```

### Task 7: Harden the image proxy and application response policy

**Files:**
- Modify: `app/image_proxy.py`, `app/main.py`
- Test: `tests/test_image_proxy.py`, `tests/test_headers.py`

**Interfaces:**
- Produces: `get_optimized_image()` with no redirects, bounded pixel decode, bounded cache, and threadpool-safe execution.

- [ ] **Step 1: Write failing image and header tests**

```python
def test_image_proxy_rejects_redirect_response(mocked_transport):
    assert request_image(mocked_transport.redirect()).status_code == 502

def test_security_headers_are_present(client):
    response = client.get("/login")
    assert response.headers["x-content-type-options"] == "nosniff"
```

- [ ] **Step 2: Verify expected failures**

Run: `uv run python -m unittest tests.test_image_proxy tests.test_headers -v`

Expected: FAIL because redirects and header policy are currently permitted.

- [ ] **Step 3: Implement safe fetch and response middleware**

Set `allow_redirects=False`, enforce source byte and decoded-pixel limits, use bounded cache eviction, call blocking work through FastAPI's threadpool, and add CSP, referrer, frame, and content-type headers compatible with Nginx.

- [ ] **Step 4: Verify focused tests pass**

Run: `uv run python -m unittest tests.test_image_proxy tests.test_headers -v`

Expected: PASS.

- [ ] **Step 5: Commit proxy hardening**

```bash
git add app/image_proxy.py app/main.py tests/test_image_proxy.py tests/test_headers.py
git commit -m "feat: harden image proxy and response headers"
```

### Task 8: Add systemd, Nginx, backup, and restore operations

**Files:**
- Create: `deploy/systemd/nmixx-radar.service`, `deploy/systemd/nmixx-radar-update.service`, `deploy/systemd/nmixx-radar-update.timer`, `deploy/systemd/nmixx-radar-hero.service`, `deploy/systemd/nmixx-radar-hero.timer`, `deploy/nginx/nmixx-radar.conf`, `scripts/backup.sh`, `scripts/restore.sh`
- Modify: `README.md`, `docs/DEPLOYMENT.md`
- Test: `tests/test_deployment_files.py`

**Interfaces:**
- Consumes: `.env` and `DATA_DIR`.
- Produces: user-installable unit files and Nginx HTTPS virtual-host example.

- [ ] **Step 1: Write failing deployment-file tests**

```python
def test_site_unit_uses_environment_file_and_runtime_directory():
    unit = Path("deploy/systemd/nmixx-radar.service").read_text()
    assert "EnvironmentFile=" in unit
    assert "WorkingDirectory=" in unit

def test_nginx_proxies_to_loopback_application_port():
    config = Path("deploy/nginx/nmixx-radar.conf").read_text()
    assert "proxy_pass http://127.0.0.1:32765" in config
```

- [ ] **Step 2: Verify expected failures**

Run: `uv run python -m unittest tests.test_deployment_files -v`

Expected: FAIL because deploy templates do not exist.

- [ ] **Step 3: Implement hardened operations templates**

Add systemd restart and sandbox settings compatible with the writable data directory, separate timer units for updates and hero refresh, an Nginx 443 TLS proxy configuration, and backup/restore scripts that operate only on the configured data directory.

- [ ] **Step 4: Verify templates and syntax**

Run: `uv run python -m unittest tests.test_deployment_files -v && systemd-analyze verify deploy/systemd/*.service deploy/systemd/*.timer && nginx -t -c "$PWD/deploy/nginx/test-nginx.conf"`

Expected: PASS for tests and available local validators; document any validator unavailable on the development host.

- [ ] **Step 5: Commit deployment support**

```bash
git add deploy scripts/backup.sh scripts/restore.sh README.md docs/DEPLOYMENT.md tests/test_deployment_files.py
git commit -m "feat: add systemd and nginx deployment templates"
```

### Task 9: Complete regression coverage and release verification

**Files:**
- Modify: `tests/test_chinese_content.py`, `README.md`
- Create: `tests/test_fresh_install.py`

**Interfaces:**
- Verifies: all previous interfaces in a clean runtime directory.

- [ ] **Step 1: Write a failing fresh-install smoke test**

```python
def test_application_bootstraps_from_sample_environment(tmp_path):
    settings = settings_from_sample(tmp_path)
    app = create_app(settings)
    assert TestClient(app).get("/health").json() == {"status": "ok"}
```

- [ ] **Step 2: Verify it fails before wiring all initialization**

Run: `uv run python -m unittest tests.test_fresh_install -v`

Expected: FAIL until application creation uses isolated settings and database setup.

- [ ] **Step 3: Complete compatibility fixes and public documentation**

Ensure the existing Chinese-content test remains valid, document RSS labels, copy-and-configure instructions, backup/restore, account bootstrap, Nginx certificates, systemd timers, and LAN HTTP tradeoffs.

- [ ] **Step 4: Run full release checks**

Run: `uv sync --frozen && uv run python -m compileall -q app && uv run python -m unittest discover -s tests -v && uvx ruff check . && uv lock --check && uvx pip-audit --local`

Expected: all checks pass with no Ruff findings and no known dependency vulnerabilities.

- [ ] **Step 5: Commit release verification**

```bash
git add tests README.md
git commit -m "test: verify fresh public installation"
```

### Task 10: Create and publish the public GitHub repository

**Files:**
- Modify: repository Git metadata only

**Interfaces:**
- Consumes: the verified `main` release commit.
- Produces: public `https://github.com/xthybot/nmixx-radar` repository with no runtime artifacts.

- [ ] **Step 1: Inspect the release candidate for secrets and ignored artifacts**

Run: `git status --ignored --short && git grep -n -I -E '10\\.[0-9]+\\.|/home/|OPENAI_API_KEY=|vapid_private|BEGIN (RSA|EC|PRIVATE)'`

Expected: no tracked secret, internal address, private path, or runtime artifact.

- [ ] **Step 2: Create the initial release commit on main**

Run: `git switch main && git merge --ff-only work/public-release`

Expected: `main` contains all verified commits.

- [ ] **Step 3: Create the GitHub repository and push only after final review**

Run: `gh repo create xthybot/nmixx-radar --public --source=. --remote=origin --push`

Expected: GitHub reports the repository URL and `origin/main` is up to date.

- [ ] **Step 4: Verify remote contents and publish handoff**

Run: `git ls-remote --heads origin && git status --short --branch`

Expected: `main` exists on origin and the local tree is clean.
