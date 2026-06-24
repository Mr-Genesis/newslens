# NewsLens â€” Firebase Auth Setup Runbook (definitive)

This is the single, ordered runbook to take NewsLens from single-user (`user_id=1`) to real multi-user Firebase auth. Follow it top to bottom.

> **Read this first â€” the repo is further along than a generic guide assumes.**
> - The backend auth seam **already exists and is tested**: `backend/app/services/auth.py` has `verify_firebase_token()` (async, `token -> uid | None`), `resolve_user(db, authorization)`, and a `get_current_user` FastAPI dependency. **Do not rewrite it.**
> - `users.firebase_uid` **already exists** (`String(128)`, nullable) **and has an Alembic migration** (`backend/migrations/versions/a7b8c9d0e1f2_wave_d_auth_firebase_uid.py`). You will **not** re-add the column â€” but you **will** add a follow-up migration to put a UNIQUE constraint on it (see 2.6; the current migration ships it plain, which is a real data-integrity gap).
> - CORS in `backend/app/main.py` (lines 227â€“238) **already allows** `capacitor://localhost` and `https://localhost`. No CORS change needed.
> - The Android Gradle is **already wired** for Firebase: `frontend/android/build.gradle` (line 11) has the `com.google.gms:google-services:4.4.4` classpath, and `frontend/android/app/build.gradle` (lines 47â€“54) conditionally applies the `com.google.gms.google-services` plugin **when `google-services.json` exists and is non-empty**. You do **not** edit Gradle to add the plugin â€” you only need to drop in `google-services.json` (4.3).
> - What's actually missing: (1) the `firebase-admin` dependency, (2) two config fields, (3) one-time Admin SDK init in `lifespan()`, (4) a UNIQUE-constraint migration on `firebase_uid`, (5) the Firebase Web SDK + a **client-only** init module + sign-in UI + Bearer-token attachment in `api.ts`, (6) the native Capacitor plugin for Android Google sign-in, and (7) wiring `get_current_user` into routes + removing/gating the no-token fallback (handed to Claude â€” see the handback list).

---

## 0) What you'll end up with + prerequisites

**End state (be precise about what this runbook does and does NOT deliver)**
- A Firebase project with **Google** and **Email/Password** sign-in enabled.
- Backend (in Docker) verifies Firebase ID tokens via `firebase-admin`. An unauthenticated request still works (falls back to the default user `id=1`); a present-but-invalid token returns `401`.
- Web app shows a sign-in screen; every `/api/*` call carries `Authorization: Bearer <idToken>` with automatic refresh.
- Android APK signs in with the **native** Google flow (web popup does **not** work in the WebView) and feeds the same ID token to the backend.
- **IMPORTANT â€” what is NOT done here:** this runbook makes auth *live* and *attaches tokens*, but it does **not** rewire the ~15 endpoints in `backend/app/api/routes.py` off `DEFAULT_USER_ID=1`. Until that cutover lands (handed to Claude), **a signed-in user still reads/writes `user_id=1` data** on every existing endpoint â€” only the new `get_current_user`-gated routes resolve a real per-user row. The "each account gets its own `users` row" end state is only reachable after the cutover **and** after the UNIQUE constraint in 2.6.

**Prerequisites**
- A Google account (for console.firebase.google.com).
- This repo cloned, and **Docker** working (the backend cannot run natively on Windows ARM â€” `greenlet` DLL failure).
- Node 20+ for the frontend; JDK 21 for the Android build.

---

## 1) Create the Firebase project + enable sign-in providers

1. Go to **https://console.firebase.google.com** â†’ **Add project** â†’ name it (e.g. `newslens-prod`) â†’ continue (Analytics optional) â†’ **Create project**.
2. Left nav â†’ **Build â†’ Authentication â†’ Get started**.
3. **Sign-in method** tab â†’ enable two providers:
   - **Google**: click it â†’ toggle **Enable** â†’ set a **Project support email** â†’ **Save**.
   - **Email/Password**: click it â†’ toggle **Enable** (leave passwordless off) â†’ **Save**.
4. **Authentication â†’ Settings â†’ Authorized domains.** `localhost` is present by default (covers `npm run dev` on :3000). Add your deployed web host if you serve the web build (e.g. your Render/Vercel domain). The `*.firebaseapp.com` auth handler domain is auto-authorized.
5. Do **not** enable Firebase Hosting â€” NewsLens serves the web build via Next and the APK via Capacitor.

You'll register the **Web app** (section 3) and the **Android app** (section 4) below; do those when you reach those sections so you copy the config straight into the right files.

---

## 2) Backend â€” Admin SDK (verify tokens for real)

### 2.1 Generate the service-account key (this is what makes verification work)
1. Firebase Console â†’ **gear (Project settings) â†’ Service accounts**.
2. Click **Generate new private key** â†’ confirm â†’ a JSON file downloads.
3. This file is a **backend secret** (it can mint tokens and read all users). Never commit it, never put it in any `NEXT_PUBLIC_*` var, never ship it in the frontend/APK.

### 2.2 Pin the SDK â€” `backend/requirements.txt`
Append under a new block (the backend Docker base is Python 3.11):

```text
# Auth (Firebase ID-token verification at app/services/auth.py)
firebase-admin==7.4.0
```

> **Version choice (changed from a 6.x recommendation â€” read why):** pin **7.4.0**, not 6.5.0. On 6.5.0 there is no `clock_skew_seconds` and no `check_revoked`. The current verifier wraps `verify_id_token` in a broad `except Exception -> None` (auth.py:32â€“34) that only `logger.debug`s the cause, so on 6.5.0 a transient clock-skew failure (`Token used too early` â€” common with Docker/mobile clock drift) is **indistinguishable from an invalid token** in the logs and surfaces as a silent `401`. 7.4.0 lets you pass `clock_skew_seconds` to tolerate drift and `check_revoked=True` to catch sign-out/disabled accounts (see the optional hardening note in 2.5). If you deliberately stay on 6.5.0, you **must** enable `debug` logging to diagnose verify failures, and accept that a revoked/disabled token keeps verifying for up to ~1 hour.

Rebuild the image so the dep lands (host `pip install` won't reach the container):

```bash
docker-compose build backend
```

### 2.3 Add two config fields â€” `backend/app/config.py`
`env_prefix` is `""` (config.py:99), so the field name **is** the env var name (uppercased). Add inside the `Settings` class after the `require_encryption` field (line 55), keeping defaults of `""` so tests and the no-auth path still boot:

```python
    # Firebase Admin SDK (verifies ID tokens at app/services/auth.py).
    # Supply ONE of these; if neither is set, the app runs with auth DISABLED
    # (resolve_user falls back to the default user â€” see app/services/auth.py).
    #   FIREBASE_CREDENTIALS_JSON       : full service-account JSON as a single-line string (best for Docker)
    #   GOOGLE_APPLICATION_CREDENTIALS  : path to the mounted service-account .json file
    firebase_credentials_json: str = ""
    google_application_credentials: str = ""
```

### 2.4 Initialize the Admin SDK exactly once â€” `backend/app/main.py`
Add this helper at module level (near `init_db` / `start_scheduler`):

```python
def init_firebase() -> bool:
    """Initialize firebase-admin EXACTLY ONCE so app/services/auth.py:verify_firebase_token works.
    No-op (logs a warning) when no credential is configured: the verifier then returns None and
    resolve_user keeps serving the default user (back-compat), so local dev still runs.
    """
    import json
    import firebase_admin
    from firebase_admin import credentials

    if firebase_admin._apps:            # already initialized (uvicorn --reload / double import)
        return True
    try:
        if settings.firebase_credentials_json:                       # inline JSON â€” best for Docker
            cred = credentials.Certificate(json.loads(settings.firebase_credentials_json))
            firebase_admin.initialize_app(cred)
            logger.info("firebase_admin_initialized", source="inline_json")
        elif settings.google_application_credentials:                # explicit file path
            cred = credentials.Certificate(settings.google_application_credentials)
            firebase_admin.initialize_app(cred)
            logger.info("firebase_admin_initialized", source="file")
        else:
            # Bare ADC. NOTE: with env_prefix="", an OS env var GOOGLE_APPLICATION_CREDENTIALS is
            # captured into settings.google_application_credentials and takes the elif branch above,
            # so this branch only runs when BOTH fields are empty (i.e. no credential at all). It
            # exists for hosted ADC (e.g. GCP metadata server). With no credential present it will
            # raise and we fall through to the warning below -> auth disabled, default user.
            firebase_admin.initialize_app()
            logger.info("firebase_admin_initialized", source="adc")
        return True
    except Exception as e:                                           # missing/bad creds -> auth disabled, not a crash
        logger.warning("firebase_admin_init_skipped", error=str(e))
        return False
```

Then call it inside `lifespan()`. The current `lifespan()` (lines 198â€“217) does `init_db()` then `start_scheduler()` then `yield`. Add the Firebase init **after** `init_db()` and **before** the scheduler:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("starting_newslens")
    try:
        await init_db()
    except Exception as e:
        logger.error("db_init_failed", error=str(e))

    try:
        init_firebase()                       # <-- ADD: one-time Admin SDK init
    except Exception as e:
        logger.error("firebase_init_failed", error=str(e))

    scheduler = None
    try:
        scheduler = await start_scheduler()
    # ...rest unchanged...
```

> Why once: `firebase_admin.initialize_app()` raises `ValueError("The default Firebase app already exists")` on a second call (uvicorn `--reload` / APScheduler imports can trigger it). The `if firebase_admin._apps: return` guard prevents that.

### 2.5 The verifier already works â€” do NOT rewrite `auth.py`
`backend/app/services/auth.py` already implements the contract: `verify_firebase_token(token) -> uid|None` (async, lazy-imports `firebase_admin`, returns `None` on any failure at lines 32â€“34) and `resolve_user(db, authorization)` (no header â†’ default user; valid uid â†’ get-or-create `User` by `firebase_uid`; present-but-invalid â†’ `HTTP 401`). The pytest suite (`backend/tests/integration/test_auth.py`) monkeypatches `auth.verify_firebase_token`, so **keep its async signature and `uid|None` return contract**. Installing the dep (2.2) + initializing once (2.4) is the entire change that makes it live.

> **Optional hardening (now in scope because you pinned 7.4.0).** In `verify_firebase_token`, pass tolerance/revocation flags to the lazy verify call:
> ```python
> decoded = fb_auth.verify_id_token(token, clock_skew_seconds=10, check_revoked=True)
> ```
> `clock_skew_seconds=10` absorbs the #1 cause of false `401`s (`Token used too early` from Docker/mobile clock drift). `check_revoked=True` catches sign-out/disabled/revoked accounts at the cost of one network call per verify (without it a revoked token keeps verifying for up to ~1h). If you change `auth.py` here, keep the function async, keep the `except Exception -> None` shape, and re-run `pytest` (it monkeypatches this function, so it won't exercise the flags â€” that's fine).

### 2.6 Add the UNIQUE constraint on `firebase_uid` (NEW â€” the shipped migration is missing it)
The existing migration (`a7b8c9d0e1f2`) adds `users.firebase_uid` as a **plain, non-unique** column (verified: `models.py:70` has no `unique=True`; the migration is a bare `add_column`). `resolve_user` does *select-by-uid â†’ insert-if-missing* (auth.py:55â€“61) with **no DB-level uniqueness**, so two concurrent first-requests for the same uid (e.g. the `api.ts` 401-retry firing a parallel call) can each see no row and insert **two** `User` rows for one Firebase account â€” an account-integrity / broken-access bug once routes go multi-user. The deferred spec itself (`docs/enhancement/FIREBASE-DEFERRED.md` line 21) says `firebase_uid` must be **unique**.

Create a follow-up migration. From the backend container/env (autogenerate is finicky on Win-ARM â€” hand-write it):

```bash
cd backend && alembic revision -m "wave D phase A: unique firebase_uid"
```

Fill the generated file:

```python
"""wave D phase A: unique firebase_uid

Revision ID: <generated>
Revises: a7b8c9d0e1f2
"""
from alembic import op

revision = "<generated>"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Partial unique index: NULLs (the back-compat default user, plus any legacy rows)
    # are allowed to repeat; only real Firebase uids must be unique.
    op.create_index(
        "uq_users_firebase_uid",
        "users",
        ["firebase_uid"],
        unique=True,
        postgresql_where=op.f("firebase_uid IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_users_firebase_uid", table_name="users")
```

> A **partial** unique index (`WHERE firebase_uid IS NOT NULL`) is required: the default user (`id=1`) and any pre-existing rows have `firebase_uid = NULL`, and a plain unique constraint would reject more than one NULL on some configs / block the back-compat row. If de-dup races already created duplicate rows in a running DB, collapse them before applying (keep the lowest `id` per uid). Pair this with making `resolve_user` upsert-safe in the Claude handback (catch `IntegrityError` and re-select) so the race degrades to a retry instead of a 500.

Then on a fresh/prod DB run all migrations:

```bash
cd backend && alembic upgrade head
```

### 2.7 Wire the credential into Docker â€” `docker-compose.yml`
Add to the **backend** service `environment:` (inline-JSON mode, sourced from your uncommitted `.env`):

```yaml
  backend:
    environment:
      - FIREBASE_CREDENTIALS_JSON=${FIREBASE_CREDENTIALS_JSON}   # from .env / secret store â€” NOT committed
      # Path-mode alternative (mount the file, point at it):
      # - GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/firebase-sa.json
      # volumes: ["./secrets/firebase-sa.json:/run/secrets/firebase-sa.json:ro"]
```

In your local `.env` (gitignored), keep the JSON **single-line, single-quoted** so the shell doesn't mangle the literal `\n` inside `private_key` (`json.loads` turns them back into real newlines):

```bash
FIREBASE_CREDENTIALS_JSON='{"type":"service_account","project_id":"newslens-prod","private_key_id":"...","private_key":"-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n","client_email":"firebase-adminsdk-xxx@newslens-prod.iam.gserviceaccount.com","client_id":"..."}'
```

> Pitfall: pass the **string** through `json.loads` (the helper does this) â€” `credentials.Certificate()` needs a parsed dict, not a JSON string.

---

## 3) Frontend â€” Web SDK

### 3.1 Register the Web app + copy config
Firebase Console â†’ **gear (Project settings) â†’ General â†’ Your apps â†’ Add app â†’ Web (`</>`)** â†’ nickname `NewsLens web` â†’ **Register app** (skip Hosting). Copy the shown `firebaseConfig` values into the `NEXT_PUBLIC_FIREBASE_*` vars below. **Copy `storageBucket` verbatim** â€” do not hand-construct it (see 3.3).

### 3.2 Install the Web SDK
```bash
cd frontend && npm install firebase
```
(Resolves Firebase JS SDK v11, modular API â€” there is **no** global `firebase` object; everything is imported.)

### 3.3 Env vars â€” `frontend/.env.local` (create it) + add placeholders to root `.env.example`
There is no `frontend/.env.example` in this repo â€” there's only the root `.env.example` (backend-oriented). Create `frontend/.env.local` for real values (it's already gitignored via the root `.gitignore` `.env.local` rule) and mirror placeholders into root `.env.example` (6).

These `NEXT_PUBLIC_*` values are **publishable** (the web `apiKey` is an app identifier, not a secret â€” it ships in every client bundle by design). Next.js inlines `NEXT_PUBLIC_*` **at build time**.

```bash
NEXT_PUBLIC_FIREBASE_API_KEY=AIzaSy...your-web-api-key
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=newslens-prod.firebaseapp.com
NEXT_PUBLIC_FIREBASE_PROJECT_ID=newslens-prod
# Copy storageBucket EXACTLY from the console. Projects created from late 2024 on default to
# <project-id>.firebasestorage.app (NOT .appspot.com). A 2026 project is almost certainly the
# .firebasestorage.app form. (Auth doesn't use storageBucket, but a wrong value breaks Storage later.)
NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=newslens-prod.firebasestorage.app
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=123456789012
NEXT_PUBLIC_FIREBASE_APP_ID=1:123456789012:web:abc123def456
# Web dev keeps the proxy; leave this unset for `npm run dev` (api.ts defaults to /api, and
# next.config.ts rewrites /api/* -> http://localhost:8000 in web mode).
# NEXT_PUBLIC_API_BASE_URL=/api
# Optional: turn on the Auth emulator wiring in dev (see 5.4). Leave UNSET in prod builds.
# NEXT_PUBLIC_USE_AUTH_EMULATOR=1
```

### 3.4 Client-only init module â€” create `frontend/src/lib/firebase.ts`
Single Firebase entry point. **This module is browser/native-only** â€” it touches `getAuth()` and `Capacitor.isNativePlatform()`, both of which throw if executed server-side. Because `api.ts` imports from here and `api.ts` is imported across the app (including code paths Next may evaluate on the server / during build), **every browser-only call is guarded with `typeof window`** so importing the module on the server is inert (and the Bearer attach simply no-ops there instead of crashing the RSC/build).

The `getApps()` guard is required because Next re-evaluates modules (HMR/RSC) and a second `initializeApp` throws *"Firebase App named '[DEFAULT]' already exists"*. On native (Capacitor) use `indexedDBLocalPersistence` â€” the default persistence is unreliable in the WebView.

```typescript
// frontend/src/lib/firebase.ts
// CLIENT-ONLY. Do not import from a Server Component without the typeof-window guards below.
import { Capacitor } from "@capacitor/core";
import { initializeApp, getApps, getApp } from "firebase/app";
import {
  getAuth,
  initializeAuth,
  indexedDBLocalPersistence,
  connectAuthEmulator,
  GoogleAuthProvider,
  signInWithPopup,
  signInWithCredential,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signOut as fbSignOut,
  type Auth,
} from "firebase/auth";

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY!,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN!,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID!,
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET!,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID!,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID!,
};

const isBrowser = typeof window !== "undefined";

// Lazily build the app/auth only in the browser/WebView. On the server these stay null.
export const app = isBrowser ? (getApps().length ? getApp() : initializeApp(firebaseConfig)) : null;

export const auth: Auth | null = !isBrowser
  ? null
  : Capacitor.isNativePlatform()
    ? initializeAuth(app!, { persistence: indexedDBLocalPersistence })
    : getAuth(app!);

// Dev-only emulator wiring, env-guarded so it NEVER ships to prod (NEXT_PUBLIC_* is inlined at build).
if (auth && process.env.NEXT_PUBLIC_USE_AUTH_EMULATOR === "1") {
  connectAuthEmulator(auth, "http://localhost:9099", { disableWarnings: true });
}

// Google sign-in branches by platform (see section 4 for the native plugin).
export async function signInWithGoogle(): Promise<void> {
  if (!auth) return;
  if (Capacitor.isNativePlatform()) {
    const { FirebaseAuthentication } = await import("@capacitor-firebase/authentication");
    const result = await FirebaseAuthentication.signInWithGoogle();      // native sheet
    const credential = GoogleAuthProvider.credential(result.credential?.idToken);
    await signInWithCredential(auth, credential);                        // feed the JS SDK
  } else {
    await signInWithPopup(auth, new GoogleAuthProvider());               // web only
  }
}

export const signInEmail = (e: string, p: string) =>
  auth ? signInWithEmailAndPassword(auth, e, p) : Promise.reject(new Error("auth unavailable"));
export const signUpEmail = (e: string, p: string) =>
  auth ? createUserWithEmailAndPassword(auth, e, p) : Promise.reject(new Error("auth unavailable"));

export async function signOut(): Promise<void> {
  if (!auth) return;
  if (Capacitor.isNativePlatform()) {
    const { FirebaseAuthentication } = await import("@capacitor-firebase/authentication");
    await FirebaseAuthentication.signOut();
  }
  await fbSignOut(auth);
}

/** Fresh, auto-refreshing ID token (or null if signed out / running server-side). */
export async function getIdToken(force = false): Promise<string | null> {
  if (!auth || !auth.currentUser) return null;
  return auth.currentUser.getIdToken(force);
}

// Dev helper to grab a token in the console (modular SDK has no global `firebase`; see 5.2).
if (isBrowser && process.env.NODE_ENV !== "production") {
  (window as unknown as { __getToken?: () => Promise<string | null> }).__getToken = () => getIdToken(true);
}
```

> `firebase.ts` and anything importing `auth` directly must be **client** code (`"use client"` or imported only from client components). The `typeof window` guards above are what keep `api.ts` safe to import anywhere.

### 3.5 Attach `Authorization: Bearer` â€” edit `frontend/src/lib/api.ts`
This is the one chokepoint: **every** endpoint helper (`getBriefing`, `getCluster`, `getClusterImpact`, `getSettings`, â€¦) routes through `fetchJSON`, so editing it once authenticates the whole app. The current `fetchJSON` (lines 8â€“27) only sets `Content-Type`. Replace it with this (keep the rest of the file unchanged). Because `getIdToken` returns `null` server-side (guarded in 3.4), an SSR/build-time call simply sends no header and hits the backend's default-user fallback â€” no crash.

```typescript
import { getIdToken } from "@/lib/firebase";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "/api";

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const doFetch = (token: string | null) =>
    fetch(`${BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}), // no token -> backend default user
        ...init?.headers,
      },
    });

  let res = await doFetch(await getIdToken());

  // Token expired/rotated since last call -> force one refresh and retry once.
  if (res.status === 401) {
    const fresh = await getIdToken(true);
    if (fresh) res = await doFetch(fresh);
  }

  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  if (res.status === 204) return undefined as T;
  return res.json();
}
```

> `getIdToken()` returns a cached token and auto-refreshes when within ~5 min of the 1-hour expiry â€” refresh is free. The 401-force-refresh-retry covers a backgrounded/long-idle tab. Do **not** hand-roll refresh.

### 3.6 Auth provider + sign-in UI
Create `frontend/src/components/AuthProvider.tsx`. Use **`onIdTokenChanged`** (not `onAuthStateChanged`) â€” it also fires on the silent ~1h refresh, keeping global state current. Guard for `auth === null` so it's safe under SSR.

```typescript
"use client";
import { createContext, useContext, useEffect, useState } from "react";
import { onIdTokenChanged, type User } from "firebase/auth";
import { auth } from "@/lib/firebase";

const AuthCtx = createContext<{ user: User | null; loading: boolean }>({ user: null, loading: true });
export const useAuth = () => useContext(AuthCtx);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    if (!auth) { setLoading(false); return; }                 // SSR / no-config: don't block render
    return onIdTokenChanged(auth, (u) => { setUser(u); setLoading(false); });
  }, []);
  return <AuthCtx.Provider value={{ user, loading }}>{children}</AuthCtx.Provider>;
}
```

Create the sign-in screen `frontend/src/app/login/page.tsx`:

```typescript
"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import { signInWithGoogle, signInEmail, signUpEmail } from "@/lib/firebase";

export default function LoginPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState(""); const [pw, setPw] = useState("");
  useEffect(() => { if (user) router.replace("/"); }, [user, router]); // already signed in -> home
  return (
    <div className="mx-auto max-w-sm p-6 space-y-4">
      <button onClick={() => signInWithGoogle().then(() => router.replace("/"))}>Continue with Google</button>
      <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="email" />
      <input type="password" value={pw} onChange={(e) => setPw(e.target.value)} placeholder="password" />
      <button onClick={() => signInEmail(email, pw).then(() => router.replace("/"))}>Sign in</button>
      <button onClick={() => signUpEmail(email, pw).then(() => router.replace("/"))}>Create account</button>
    </div>
  );
}
```

Wire `AuthProvider` into `frontend/src/app/layout.tsx`. The current layout (Server Component) wraps `<SplashScreen /> <NavBar /> <main>{children}</main> <BottomTabBar />` in `<ThemeProvider>` (lines 60â€“67). Nest `AuthProvider` (a client component) inside it:

```tsx
        <ThemeProvider>
          <AuthProvider>
            <SplashScreen />
            <NavBar />
            <main className="flex-1 pt-[var(--page-top)] pb-[var(--page-bottom)]">
              {children}
            </main>
            <BottomTabBar />
          </AuthProvider>
        </ThemeProvider>
```

(Add `import { AuthProvider } from "@/components/AuthProvider";` at the top of `layout.tsx`.)

> Gate only the per-user screens (`/settings`, `/saved`) on `useAuth().user`. Leave the briefing/feed reachable signed-out â€” the backend's no-token fallback serves the default user, preserving today's behavior during rollout. (That fallback is also a security item â€” see 6 and the handback list: it must be removed/flag-gated before the multi-user cutover.)

### 3.7 Validate the frontend build + tests (REQUIRED â€” CLAUDE.md mandates this)
After adding `firebase.ts`, `AuthProvider.tsx`, `login/page.tsx`, and the `api.ts` edit, run the repo's mandated checks. The `typeof window` guards in 3.4 exist specifically so these pass â€” if the build throws `Capacitor is not defined` or a Server/Client boundary error, a guard was dropped.

```bash
cd frontend && npm run build        # full --webpack production build â€” must succeed
cd frontend && npx vitest run       # unit tests
cd frontend && npm run lint:copy    # copy guard (blocks internal jargon in UI strings)
```

---

## 4) Capacitor / Android

**Why web popup fails in the WebView:** `signInWithPopup` opens a second window the Android WebView can't manage, and `signInWithRedirect` relies on a cross-origin iframe + third-party storage that Chrome 115+ partitioning blocks for the `https://localhost`/`capacitor://localhost` origin. **For the APK, use the native plugin** (the `firebase.ts` `signInWithGoogle` above already branches on `Capacitor.isNativePlatform()`). On modern Android the plugin's Google flow uses Credential Manager, which is why the `androidxCredentials` version is set in 4.2.

### 4.1 Install the native plugin â€” pin to match Capacitor 8, then verify the peer dep
The repo is on **Capacitor 8** (`@capacitor/android`, `/cli`, `/core` are all `^8.3.0`). `@capacitor-firebase/authentication` tracks Capacitor majors and historically lags, so an **unpinned** `npm install` can resolve a build whose `peerDependencies` want `@capacitor/core@7.x` â†’ ERESOLVE / a silent runtime mismatch. Do **not** rely on "pick the matching major" alone:

```bash
cd frontend
# Pin the Capacitor-8-compatible line explicitly (adjust to the latest published 8.x):
npm install @capacitor-firebase/authentication@^8.0.0

# THEN verify the peer dep actually points at Capacitor 8 before building:
npm ls @capacitor/core
npm view @capacitor-firebase/authentication@$(node -p "require('@capacitor-firebase/authentication/package.json').version") peerDependencies
```
If `peerDependencies` still names `@capacitor/core: ^7` (i.e. an `8.x` plugin isn't published yet), fall back to the highest plugin version whose peer range includes `^8`, or install with `--legacy-peer-deps` **only after** confirming the plugin's native code supports Capacitor 8 â€” and record the exact pinned version. A peer mismatch here is the most common reason native Google sign-in compiles but returns a null `idToken`.

### 4.2 Configure the plugin â€” `frontend/capacitor.config.ts`
The current config is `{ appId: "com.newslens.app", appName: "NewsLens", webDir: "out" }`. Add a `plugins` block (keep the existing fields):

```typescript
import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.newslens.app',
  appName: 'NewsLens',
  webDir: 'out',
  plugins: {
    FirebaseAuthentication: {
      skipNativeAuth: false,       // use the REAL native flow, then bridge into the JS SDK
      providers: ['google.com'],
    },
  },
};

export default config;
```

Add to `frontend/android/variables.gradle` (current `ext { ... }` block) so the Google native SDK + Credential Manager are pulled into Gradle, then sync:

```gradle
ext {
    // ...existing minSdkVersion / compileSdkVersion / targetSdkVersion ...
    rgcfaIncludeGoogle = true
    androidxCredentialsVersion = '1.3.0'
}
```
```bash
cd frontend && npx cap update android
```

> **No Gradle plugin edits needed.** `frontend/android/build.gradle` (line 11) already has the `com.google.gms:google-services:4.4.4` classpath, and `frontend/android/app/build.gradle` (lines 47â€“54) already conditionally runs `apply plugin: 'com.google.gms.google-services'` **when `google-services.json` is present and non-empty**. So the only thing that makes the native config live is dropping in `google-services.json` (4.3). Without that file the conditional skips and native Google sign-in returns a null `idToken` even with the SHA-1 added.

### 4.3 Register the Android app + SHA-1 + `google-services.json`
1. Firebase Console â†’ **Project settings â†’ Your apps â†’ Add app â†’ Android**. Package name **exactly** `com.newslens.app` (must match `capacitor.config.ts` `appId`).
2. Get the **debug SHA-1** and add it (mandatory â€” without it native Google sign-in returns a null `idToken`):
   ```bash
   cd frontend/android && ./gradlew signingReport
   # copy the SHA1 under "Variant: debug" -> Console > Project settings > your Android app > Add fingerprint
   ```
3. **Download `google-services.json`** â†’ place at `frontend/android/app/google-services.json`. This file carries **publishable client config only** (the same Android/web API key + project IDs that ship inside the APK anyway) â€” keeping it out of git is hygiene, **not** secret protection. **But it is currently NOT ignored:** `frontend/android/.gitignore` line 65 has `# google-services.json` **commented out**. Uncomment it (or add `app/google-services.json`) **before** you commit, or the file lands in the repo:
   ```bash
   # in frontend/android/.gitignore, change line 65 from:
   #   # google-services.json
   # to:
   #   google-services.json
   ```
4. Authorized domains: the native flow uses the auto-authorized `*.firebaseapp.com` handler â€” no extra domain needed for the APK.
5. For a release APK later, repeat step 2 with the **release keystore** SHA-1 and re-download `google-services.json`.

### 4.4 Build env â€” `NEXT_PUBLIC_*` are inlined at build time
`npm run build:android` already injects `NEXT_PUBLIC_API_BASE_URL=http://10.0.2.2:8000`, but it does **not** inject the `NEXT_PUBLIC_FIREBASE_*` vars â€” those must be present in `frontend/.env.local` (or the build env) **when you build**, or the bundled Firebase config is empty and sign-in silently no-ops. Also ensure `NEXT_PUBLIC_USE_AUTH_EMULATOR` is **unset** for any APK you actually ship.

### 4.5 Physical-device testing (no emulator on Win-ARM)
`10.0.2.2` is an **emulator-only** alias and will **not** resolve on a real phone. Pick one:

```bash
# Option A â€” reverse-tunnel the phone's localhost to your PC, then build pointing at localhost
adb reverse tcp:8000 tcp:8000
# then build with NEXT_PUBLIC_API_BASE_URL=http://localhost:8000

# Option B â€” point at your PC's LAN IP (phone + PC on same Wi-Fi)
# NEXT_PUBLIC_API_BASE_URL=http://192.168.1.50:8000

cd frontend && npm run build:android && npm run apk:debug
# install: frontend/android/app/build/outputs/apk/debug/app-debug.apk  (adb install -r ...)
```
Tap **Continue with Google** â†’ the **native account picker** appears (proof the native plugin, not the web popup, is running) â†’ app loads briefing. Backend log shows `resolve_user` finding/creating a `User` by `firebase_uid`.

---

## 5) Local testing + emulator option + end-to-end verification

### 5.1 Backend tests stay green â€” but understand what they do NOT prove
```bash
cd backend && pytest
```
The suite (`backend/tests/integration/test_auth.py`) **monkeypatches `auth.verify_firebase_token`**, so a green run proves the get-or-create/401/fallback logic â€” it proves **nothing** about the live Admin SDK or real token verification. Do not treat passing tests as evidence that real auth works. The real proof is 5.2.

### 5.2 Verify the backend against Docker with a REAL token (this is the actual validation)
```bash
docker-compose up -d db
docker-compose build backend && docker-compose up -d backend
cd backend && alembic upgrade head     # applies firebase_uid + the new UNIQUE index

# 1) Confirm the Admin SDK actually initialized (not the warning path):
docker-compose logs backend | grep firebase_admin_initialized   # expect source=inline_json (or file/adc)

# 2) Health + no-auth fallback + invalid-token rejection:
curl -s localhost:8000/health                                   # {"status":"ok","db":"connected"}
curl -s localhost:8000/briefing                                 # 200, default-user data (NO auth header)
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Bearer badtoken" localhost:8000/briefing   # expect 401
```
Now get a **real** ID token from the running frontend. The app uses the **modular** SDK, so there is **no** global `firebase` object â€” `firebase.auth()...` will throw `firebase is not defined`. Instead:
- Read the `Authorization` header off any `/api/*` request in the browser **Network** tab, **or**
- In dev, use the helper exposed in 3.4: open the console and run `await window.__getToken()`.

Call again with that token and confirm a backend log line shows `resolve_user` resolving/creating a `User` keyed on the `firebase_uid` (not `id=1`):
```bash
curl -s -H "Authorization: Bearer <real-id-token>" localhost:8000/briefing
docker-compose logs backend | tail -n 20   # look for the firebase_uid being resolved
```
> If verification fails on real tokens but `badtoken` correctly 401s, suspect clock skew: with the recommended 7.4.0 + `clock_skew_seconds=10` (2.5) this is handled; on 6.5.0 enable `debug` logging to see the `firebase_verify_failed` cause.

### 5.3 Verify the web app end to end
```bash
cd frontend && npm run dev      # http://localhost:3000  (proxies /api -> :8000 via next.config rewrites)
```
Sign in at `/login`. In the **Network** tab, confirm `/api/*` requests carry `Authorization: Bearer â€¦`. Leave the tab idle > 1h (or sign out/in) and confirm the token rotates without a re-login (the 401-retry + silent refresh).

> **Win-ARM note:** local browser QA of the proxied `/api` path can hang on this machine. If `/api/*` stalls, verify the token flow with `npm run build` + the curl checks against Docker (5.2) instead of relying on the dev proxy.

### 5.4 Optional â€” Firebase Auth emulator (offline, no real project)
For fully local testing without hitting Google:
```bash
npm i -g firebase-tools
firebase init emulators        # select Authentication; default port 9099
firebase emulators:start
```
- **Frontend:** the emulator wiring is already in `firebase.ts` (3.4) behind `NEXT_PUBLIC_USE_AUTH_EMULATOR === "1"`. Set `NEXT_PUBLIC_USE_AUTH_EMULATOR=1` in `frontend/.env.local` **for dev only**, and never in a prod/APK build (it's inlined at build time â€” a stray `1` would point real users at `localhost:9099`).
- **Backend:** set `FIREBASE_AUTH_EMULATOR_HOST=localhost:9099` (use `host.docker.internal:9099` from inside Docker â€” and confirm the verify path actually reads it; `firebase-admin` checks this env var before doing signature verification). With the emulator set, **don't pass a real service-account credential** â€” initialize with an explicit anonymous credential + projectId so the Admin SDK doesn't try ADC on a clean Docker image:
  ```python
  from firebase_admin import credentials
  firebase_admin.initialize_app(credentials.AnonymousCredentials(), options={"projectId": "<your-project-id>"})
  ```
  (Passing only `options={"projectId": ...}` with no credential still makes the SDK attempt ADC for the app and can emit credential errors at init; the anonymous credential avoids that.)
- Tokens minted by the emulator verify only against the emulator. Don't mix emulator and live creds.

---

## 6) Security â€” do / don't

**Commit (safe):**
- `NEXT_PUBLIC_FIREBASE_*` values â€” publishable app identifiers, not secrets. Real protection is enabled providers + Authorized domains + Security Rules, **not** hiding the web `apiKey`. Do **not** Fernet-encrypt these the way the app encrypts OpenAI/Gemini keys.
- The `firebase-admin` pin and all the code from sections 2â€“4.

**Never commit â€” make these MANDATORY pre-commit, not "if not, add":**
- The service-account JSON file and `FIREBASE_CREDENTIALS_JSON` value live in `.env`. Root `.gitignore` already ignores `.env` / `.env.local` âœ….
- `/secrets/*.json` is **NOT** currently in the root `.gitignore` (verified). If you use path-mode (2.7), add it.
- `frontend/android/app/google-services.json` is **NOT** ignored â€” the line in `frontend/android/.gitignore` is **commented out** (verified, line 65). You **must** uncomment/add it (4.3) before committing.

Apply these `.gitignore` changes now:
```gitignore
# root .gitignore â€” add:
/secrets/*.json

# frontend/android/.gitignore line 65 â€” uncomment to:
google-services.json
```

**`.env.example` additions** (placeholders only, no real values â€” the repo's `.env.example` currently has NO Firebase entries):
```bash
# --- Firebase: backend (service account, SECRET â€” backend/Docker only) ---
FIREBASE_CREDENTIALS_JSON=
# GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/firebase-sa.json   # path-mode alternative

# --- Firebase: frontend web config (publishable, inlined at build time) ---
NEXT_PUBLIC_FIREBASE_API_KEY=
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=
NEXT_PUBLIC_FIREBASE_PROJECT_ID=
NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=
NEXT_PUBLIC_FIREBASE_APP_ID=
# NEXT_PUBLIC_USE_AUTH_EMULATOR=1   # dev only â€” NEVER set in a prod/APK build
```

**Two access-control items that MUST be closed before multi-user launch (not optional):**
1. **`firebase_uid` uniqueness** â€” done in 2.6. Without it, concurrent first-requests create duplicate accounts for one identity.
2. **The no-token â†’ `DEFAULT_USER_ID=1` fallback** (`auth.py:49â€“50`) â€” fine for the single-user MVP and the rollout window, but once routes carry real per-user data it is a **broken-access-control vector**: any request that simply *omits* the `Authorization` header is served as user 1, reading/writing that account's data. Before the multi-user cutover, **remove the fallback or gate it behind an explicit feature flag** so unauthenticated requests get `401` instead of silently becoming user 1. This is part of the Claude handback.

**Rule of thumb:** the service account is a write-capable backend secret (mints custom tokens, reads all users) â€” it stays server-side in Docker env/secret store and never touches `NEXT_PUBLIC_*` or the APK.

---

## After this runbook: hand off to Claude for the route cutover + RLS

This guide makes auth **live** and attaches tokens. The remaining mechanical + security-critical work is best done by Claude after you confirm the token flow works end to end (5.2). See the handback list for exactly what to give Claude â€” note it explicitly includes **removing/gating the no-token fallback** and **making `resolve_user` upsert-safe**, not just swapping `DEFAULT_USER_ID` for `Depends(get_current_user)`.

---

## Appendix — structured reference

### Backend env vars
- `FIREBASE_CREDENTIALS_JSON`
- `GOOGLE_APPLICATION_CREDENTIALS`
- `FIREBASE_AUTH_EMULATOR_HOST`
- `DATABASE_URL`
- `OPENAI_API_KEY`
- `ENCRYPTION_KEY`

### Frontend env vars
- `NEXT_PUBLIC_FIREBASE_API_KEY`
- `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN`
- `NEXT_PUBLIC_FIREBASE_PROJECT_ID`
- `NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET`
- `NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID`
- `NEXT_PUBLIC_FIREBASE_APP_ID`
- `NEXT_PUBLIC_API_BASE_URL`
- `NEXT_PUBLIC_USE_AUTH_EMULATOR`

### Hand back to Claude (so I can wire live auth + RLS)
- The Firebase service-account JSON (single-line) so Claude can set FIREBASE_CREDENTIALS_JSON in the uncommitted .env / docker-compose backend env. Never paste it into chat history you keep â€” treat it as a secret.
- Confirmation that `docker-compose logs backend` shows `firebase_admin_initialized` (source=inline_json/file/adc) AND that a real ID token resolves a users row keyed on firebase_uid (the 5.2 end-to-end check passed). Green pytest is NOT sufficient.
- Instruct Claude to rewire the ~15 `DEFAULT_USER_ID=1` / hardcoded user_id call sites in backend/app/api/routes.py (and the pipeline default at embeddings.py:41 â€” keep ingest/cluster jobs system-level; only user-scoped reads/writes change) onto `Depends(get_current_user)`.
- Instruct Claude to REMOVE or feature-flag the no-token -> DEFAULT_USER_ID=1 fallback in backend/app/services/auth.py (resolve_user lines 49â€“50) before multi-user launch, so unauthenticated requests get 401 instead of silently acting as user 1.
- Instruct Claude to make resolve_user upsert-safe (catch IntegrityError from the new UNIQUE firebase_uid index and re-select) so the get-or-create race degrades to a retry, not a 500.
- Instruct Claude to add Postgres Row-Level Security (RLS) on user-scoped tables after the route cutover, scoping rows by the resolved user id.
- The pinned @capacitor-firebase/authentication version you actually installed (and the output of `npm ls @capacitor/core` + the plugin's peerDependencies) so Claude knows the native plugin matches Capacitor 8.
- Whether you enabled the 7.4.0 hardening flags (clock_skew_seconds / check_revoked) in verify_firebase_token, so Claude keeps them when touching auth.py.

### Secrets — never commit
- The Firebase service-account JSON file (Generate new private key download) â€” backend secret, can mint tokens and read all users.
- FIREBASE_CREDENTIALS_JSON value in .env / docker-compose (the inline service-account JSON).
- frontend/android/app/google-services.json â€” NOT a backend secret (publishable client config) but the gitignore line is currently COMMENTED OUT at frontend/android/.gitignore:65; uncomment it before committing.
- Any path-mode service-account file under /secrets/*.json â€” add /secrets/*.json to root .gitignore (currently absent).
- ENCRYPTION_KEY and OPENAI_API_KEY in .env (existing app secrets, already gitignored via .env).

---
_Generated by the firebase-setup-guide workflow (7 agents: repo grounding + Admin/Web/Capacitor research, synthesize, adversarial critique, finalize). 14 corrections applied._

