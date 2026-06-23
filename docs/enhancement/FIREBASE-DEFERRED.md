# Firebase — Auth + Notifications (SCOPED & PARKED)

> Decision (2026-06-23): Scope now, **build later**. NewsLens stays **single-user** (`user_id=1`)
> until this lands. Parked because multi-user auth is a large, cross-cutting lift and the
> enhancement roadmap (E0–E8) delivers more user value first. This doc is the spec to pick up later.

## Why Firebase (vs alternatives)

- **One SDK for both needs we have**: Firebase **Auth** (Google sign-in out of the box) + **Cloud Messaging (FCM)** for push — including the future notification-engine ideas (daily briefing, "breaking in your topics", trivia streaks).
- Folds in **"Google Sign-in"** (one of the three Google asks) natively — no separate Google Cloud OAuth client wiring.
- Free tier is ample for a personal app.

## A. Authentication (Firebase Auth)

### What it unlocks
- Real multi-user: each user gets their own interests, profession, saved items, API keys, history.
- Makes personalization (E3) and per-(user) impact (E6) genuinely testable.

### Backend changes
- Add `firebase-admin` to `requirements.txt`; init with a service-account credential (env: `FIREBASE_CREDENTIALS_JSON` or path).
- `users` table: add `firebase_uid` (unique), `email`, `display_name`, `photo_url`, `created_at` (exists).
- New dependency `get_current_user()` (FastAPI `Depends`): read `Authorization: Bearer <ID token>` → `firebase_admin.auth.verify_id_token` → resolve/create local `users` row by `firebase_uid`.
- **Replace the ~15 hardcoded `user_id=1` call sites** (`routes.py` etc.) and the pipeline default (`embeddings.py:41`) with the resolved user. Pipeline jobs (ingest/cluster) stay system-level; only user-scoped reads/writes change.
- Migration: backfill the existing single user; gate new endpoints behind auth.

### Frontend changes
- Add Firebase JS SDK + a **Login screen** (Google sign-in button; email-link optional).
- Store the ID token; attach `Authorization: Bearer` in `fetchJSON` (`lib/api.ts:8`).
- Auth guard / redirect; "signed in as" in Settings/Profile (replaces the cosmetic greeting).
- Capacitor: use the Firebase Auth web flow inside the WebView (or `@capacitor-firebase/authentication` plugin for native Google sign-in).

### Effort (rough): backend ~M, frontend ~M, migration ~S. Net ~1–2 focused builds.

## B. Push notifications (Firebase Cloud Messaging)

> Depends on Auth (need a user → device-token mapping).

### Backend
- `device_tokens` table: `user_id`, `token`, `platform`, `created_at`, `last_seen`.
- Endpoints: `POST /devices` (register token), `DELETE /devices/{token}`.
- Send service via `firebase-admin` messaging; triggers (APScheduler jobs):
  - **Daily briefing ready** (morning, per locale).
  - **Breaking in your topics** (new high-coherence cluster matching user preferences).
  - **Trivia streak / daily quiz** nudge (engagement loop — ties to E8).
- Respect quiet hours + per-type opt-in (a `notification_prefs` JSON on the user).

### Frontend / Capacitor
- Web: FCM JS SDK + service worker (`firebase-messaging-sw.js`) for web push.
- Android (Capacitor): `@capacitor/push-notifications` + FCM; register token on login; handle foreground/background.
- Settings UI: notification toggles per type + quiet hours.

### Effort (rough): backend ~M, Android wiring ~M (physical device needed — emulator unsupported on Win-ARM).

## Prerequisites (when we start)
1. Create a **Firebase project**; add a **Web app** (config) and **Android app** (`google-services.json`, package `com.newslens.app`).
2. Generate a **service-account key** for `firebase-admin` (backend).
3. Enable **Google** provider in Firebase Auth; add authorized domains (Render URL, localhost).
4. Enable **Cloud Messaging**.

## Sequencing
Build **after E0–E8** (or at least after E3 personalization), so auth lands on top of real per-user value. Auth is a prerequisite for FCM. The Gemini/feature work does **not** depend on auth (stays single-user-friendly).

## Open questions
- Email-link / anonymous sign-in in addition to Google?
- Do we gate the whole app behind login, or allow anonymous browse + sign-in to personalize? (Recommend the latter — lower acquisition friction.)
