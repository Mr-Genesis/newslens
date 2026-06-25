// CLIENT-ONLY Firebase entry point. Safe to import anywhere because every browser/native call is
// guarded by `typeof window` — on the server `app`/`auth` are null and getIdToken() returns null,
// so api.ts simply sends no Authorization header during SSR/build (backend default-user fallback).
import { Capacitor } from "@capacitor/core";
import { getApp, getApps, initializeApp } from "firebase/app";
import {
  GoogleAuthProvider,
  connectAuthEmulator,
  createUserWithEmailAndPassword,
  getAuth,
  indexedDBLocalPersistence,
  initializeAuth,
  signInWithCredential,
  signInWithEmailAndPassword,
  signInWithPopup,
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

// getApps() guard: Next re-evaluates modules (HMR/RSC); a second initializeApp throws.
export const app = isBrowser ? (getApps().length ? getApp() : initializeApp(firebaseConfig)) : null;

function makeAuth(): Auth | null {
  if (!isBrowser || !app) return null;
  try {
    if (Capacitor.isNativePlatform()) {
      // indexedDB persistence is the reliable choice inside the Android WebView.
      try {
        return initializeAuth(app, { persistence: indexedDBLocalPersistence });
      } catch {
        return getAuth(app); // already initialized (HMR) — initializeAuth twice throws
      }
    }
    return getAuth(app);
  } catch {
    return null; // missing/invalid config (e.g. test env, unconfigured build) → degrade to signed-out
  }
}

export const auth: Auth | null = makeAuth();

// Dev-only emulator wiring — env-guarded so it NEVER ships to a prod/APK build.
if (auth && process.env.NEXT_PUBLIC_USE_AUTH_EMULATOR === "1") {
  connectAuthEmulator(auth, "http://localhost:9099", { disableWarnings: true });
}

/** Google sign-in: native account sheet inside Capacitor, popup on the web. */
export async function signInWithGoogle(): Promise<void> {
  if (!auth) return;
  if (Capacitor.isNativePlatform()) {
    const { FirebaseAuthentication } = await import("@capacitor-firebase/authentication");
    const result = await FirebaseAuthentication.signInWithGoogle(); // native sheet (Credential Manager)
    const credential = GoogleAuthProvider.credential(result.credential?.idToken);
    await signInWithCredential(auth, credential); // bridge the native result into the JS SDK
  } else {
    await signInWithPopup(auth, new GoogleAuthProvider());
  }
}

export const signInEmail = (email: string, password: string) =>
  auth ? signInWithEmailAndPassword(auth, email, password) : Promise.reject(new Error("auth unavailable"));

export const signUpEmail = (email: string, password: string) =>
  auth ? createUserWithEmailAndPassword(auth, email, password) : Promise.reject(new Error("auth unavailable"));

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

// Dev helper to grab a token in the console (modular SDK has no global `firebase`): await __getToken()
if (isBrowser && process.env.NODE_ENV !== "production") {
  (window as unknown as { __getToken?: () => Promise<string | null> }).__getToken = () => getIdToken(true);
}
