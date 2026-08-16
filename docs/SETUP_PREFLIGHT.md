# Preflight — environment check before Phase 0

**Destination:** `docs/SETUP_PREFLIGHT.md`

**For Claude Code:** run this before any code is written, at the very first
session. Do not assume any tool exists. Do not install anything without asking.
Report the full result first, in one message, then wait.

**Why this exists:** Claude Code does not inspect the machine on its own. It
finds a missing tool when a command fails, and by then it may have gone some way
down a wrong path. Ten minutes here saves an evening later.

---

## 1. Run every check, then report

Run all of these, even after the first one fails. The user needs the whole
picture at once, not one missing tool at a time.

```bash
# Operating system and shell
uname -a 2>/dev/null || ver

# Version control
git --version
git config user.name
git config user.email

# Containers — the whole stack runs here
docker --version
docker compose version
docker info            # confirms the daemon is actually running, not just installed

# Python
python3 --version      # need 3.12
which uv || echo "uv not installed"
pip --version

# Node — for the client
node --version         # need 20 LTS
npm --version

# Disk space (Postgres image + node_modules + Playwright browsers ≈ 4–6 GB)
df -h .

# Ports that must be free: 5432 (db), 8000 (api), 5173 (client)
# Linux/macOS:
lsof -i :5432 -i :8000 -i :5173 2>/dev/null || echo "ports check unavailable"
# Windows PowerShell:
# Get-NetTCPConnection -LocalPort 5432,8000,5173 -ErrorAction SilentlyContinue
```

## 2. Report in this shape

| Tool | Required | Found | OK? |
|---|---|---|---|
| Docker Engine | any current | | |
| Docker Compose | v2 (`docker compose`, not `docker-compose`) | | |
| Docker daemon | running | | |
| Git | any, with user.name and user.email set | | |
| Python | 3.12 | | |
| Node | 20 LTS | | |
| Free disk | ≥ 10 GB | | |
| Ports 5432 / 8000 / 5173 | free | | |

Then list, in priority order, exactly what the user must install, with the
command for **their** operating system. Do not run installers yourself. Do not
use `sudo` without asking. Tell the user what to run and wait for them to
confirm it worked.

## 3. Notes on specific tools

**Docker is the one that matters most.** The entire stack runs in Compose, and
the plan is explicit that Postgres must never be installed on the host — so that
"it works on my machine" and "it works at the review" are the same sentence. On
Windows this means Docker Desktop with the WSL 2 backend. On Linux, the user must
be in the `docker` group, or every command needs `sudo`, which becomes miserable
fast. Check `docker info` and not just `docker --version`: the binary can exist
while the daemon is not running, which produces confusing errors later.

**Compose v2 only.** `docker compose version` (space) must work. The old
`docker-compose` (hyphen) is a different, older tool and the plan's compose file
assumes v2.

**Git identity.** If `user.name` and `user.email` are unset, commits fail or land
anonymously. The commit history is evidence that this is individual work, which
matters for the grade — so it needs to be right from commit one, not fixed later.

**Python 3.12 and Node 20** are only needed on the host for editor support and
running tooling outside containers. The container images pin their own versions.
If the host has different versions, say so but do not treat it as blocking.

**Port 5432 is the common conflict.** If the user has Postgres or pgAdmin
installed from an earlier project, the container will fail to bind. The fix is to
stop the host service, or change the published port in `docker-compose.yml` —
ask the user which, since the second one changes a file the plan specifies.

**Playwright** (needed at Phase 4) downloads browser binaries on first install,
roughly 1–2 GB. Mention it at Phase 4, not now, but count it in the disk estimate.

**k6** (needed at Phase 8, experiment E5) is a separate binary. Do not install it
now. Flag it at Phase 7 so the user has time.

## 4. Accounts and access to confirm with the user

- GitHub account and an empty remote repository — CI must run from week 1, while
  there is almost nothing to test. Adding CI to a large broken codebase in week 8
  is a day that will not exist.
- The user should confirm that GitHub Actions minutes are available on their
  account (free tier is enough for a public repository).

## 5. Optional, but worth ten minutes

Run `claude doctor` once. It checks Claude Code's own installation — Node
version, network access, authentication, config integrity — and flags what is
broken. It does **not** check Docker, Python, or anything in this document. It is
worth running once so that install problems and project problems do not get mixed
together later.

## 6. Exit criterion for preflight

- [ ] Every row in the table above is green, or has an explicit decision from the
      user to proceed without it.
- [ ] `docker run --rm hello-world` succeeds.
- [ ] An empty Git repository exists locally, with a remote configured, and one
      commit pushed.

Only then start Phase 0.
