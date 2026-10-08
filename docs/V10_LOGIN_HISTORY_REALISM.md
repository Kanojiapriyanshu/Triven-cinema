# Triven Cinema v10 - Login, Previous Chats, and Realism

## What changed

### 1. Demo email + OTP login

Cinema Studio has an account gate. A user enters an email and the API creates a cryptographically random six-digit OTP. This document describes the earlier private demo, where the code appeared in the login screen. Production at `cinema.devansh.info` defaults to real SMTP delivery; a restricted demo requires both `DEMO_AUTH_SHOW_OTP=true` and `ALLOW_PRODUCTION_DEMO_AUTH=true`. Use [the production runbook](PRODUCTION.md) for deployment.

The OTP is stored only as an HMAC digest, expires, has a bounded attempt count, and is exchanged for an HttpOnly signed session cookie. A returning email maps to the same stable workspace, which means Elements, billing/integration state, generated assets, and chat history remain attached to the account.

Production warning: anyone reaching the demo login can sign in as any email, including existing accounts. Restrict demo access at the proxy. Before a public production launch, set both demo flags to `false` and deliver the OTP through a verified SMTP provider.

### 2. Account-owned Previous Chats

The sidebar history is no longer browser-only. Chats are stored in `storage/chats/chats.sqlite3`, scoped by the authenticated workspace, and autosaved from the Studio. Opening or deleting a previous chat updates the account-backed history.

The old v9 localStorage history can be migrated once only when the signed-in account has an empty server history. After that, local fallback storage is keyed by account ID, preventing one account from reading another account's cache on a shared browser.

### 3. Real-skin final-render path

Final 1080p/4K Modal renders keep the existing production DFR path with the diffusion video VAE and the official Refine Details IC-LoRA pass. The DFR path deliberately stays on the LTX 2.5 distilled checkpoint: the official DFR pipeline expects the distilled transformer rather than the full/dev transformer.

For `Real Skin`, Refine Details uses a tile-safe photographic-detail prompt to rebuild fine surface texture instead of explicitly asking every tile to repaint skin or a face. This reduces the waxy/soft VAE look without unnecessarily changing the scene.

`Identity Max` now requires an identity-mode Character Element. Use a sharp, naturally lit, minimally processed real photo as that Element's primary reference. The Character Element steers the base Ingredients identity generation; the final tiled Refine Details pass then reconstructs texture from the generated clip.

Triven deliberately does **not** pass an arbitrary raw portrait directly to Refine Details at frame `-1`. LTX supports that reference mode, but its tiled workflow expects the image to be spatially aligned to the output canvas. A raw portrait can reach the wrong tiles and reduce identity similarity, so this patch keeps that feature off until subject-aware alignment is implemented.

Prompt-only faces can still look synthetic because the model must invent identity and microtexture. For recurring human presenters, Character Element + Identity Max + final 1080p/4K is the preferred path.

## New persistent state

Back up these alongside the existing job/billing/integration databases:

- `storage/auth/auth.sqlite3`
- `storage/chats/chats.sqlite3`
- `storage/elements/elements.sqlite3`

`scripts/backup_state.py` now includes them.

## Important environment variables

```env
AUTH_ENABLED=true
DEMO_AUTH_SHOW_OTP=true
AUTH_OTP_TTL_SECONDS=600
AUTH_OTP_MAX_ATTEMPTS=5
AUTH_SESSION_DAYS=30
TRIVEN_SECRET_KEY="replace-with-a-long-random-secret"
CHAT_HISTORY_LIMIT=100
CHAT_WORKSPACE_MAX_BYTES=1500000
```

The settings above show local demo mode. On a production host, additionally set `ALLOW_PRODUCTION_DEMO_AUTH=true` for a restricted demo without SMTP. For email-verified sign-in, set both demo flags to `false` and configure a real SMTP delivery provider.

## Modal redeploy required

Because `modal/app.py` and `modal/ltx_worker.py` changed, redeploy the worker after applying this version:

```bash
set -a
source .env
set +a
modal deploy modal/app.py
```

No model checkpoint change is required by this patch.
