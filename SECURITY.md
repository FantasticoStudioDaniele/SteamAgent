# Security Policy

## Supported versions

SteamAgent is in early beta (`0.x`). Security fixes land on the latest `main`;
there is no separate maintenance branch yet, so please always run the latest
commit.

| Version | Supported |
|---|---|
| latest `main` / `0.1.x` | ✅ |
| older | ❌ |

## Reporting a vulnerability

Please report security issues **privately** — do **not** open a public issue.

Use GitHub's private reporting on this repository:
**Security → Advisories → “Report a vulnerability”**
(<https://github.com/FantasticoStudioDaniele/SteamAgent/security/advisories/new>).

We aim to acknowledge a report within **7 days** and will agree a disclosure
timeline with you. Please give us a reasonable window to ship a fix before any
public disclosure.

## What this tool touches (threat model)

SteamAgent automates login to **your own** Steam partner account and stores the
collected data locally. The sensitive assets all live **on the machine that runs
it**:

- `.env` — the bot account password and, optionally, the TOTP `shared_secret`,
  in **plaintext**.
- `data/storage_state.json` — a **live authenticated session** for both partner
  portals: reusable without the password or a 2FA code, so it is equivalent to
  the account itself.
- `data/*.db` and `data/raw/` — your financial and marketing data.

On POSIX these files are written with restrictive permissions (`.env` and the
session at `0600`, `data/` at `0700`); `steam-agent doctor` warns if they become
group- or other-readable.

### In scope

- Bugs that leak or expose `.env`, `storage_state.json`, or the local database.
- Flaws in credential/session handling, the login flow, or the collectors.
- Vulnerable dependencies that are actually reachable from the code.

### Out of scope

- Using SteamAgent against an account you do not own (against Steam's Terms — and
  not something this project supports).
- The fact that secrets sit in a plaintext `.env`: that is a documented design
  choice, mitigated by the file-permission hardening above. Prefer manual 2FA
  mode on shared machines.

## A note for users

The TOTP `shared_secret` generates valid Steam Guard codes indefinitely — it is a
**permanent 2FA bypass**. Treat it like the account password: only set it on a
locked-down server, and prefer manual-code login on laptops. If it ever leaks,
remove the authenticator from the Steam mobile app to rotate the secret.
