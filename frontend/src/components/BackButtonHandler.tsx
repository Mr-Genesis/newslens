"use client";

import { useEffect, useRef } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Capacitor } from "@capacitor/core";

import { ToastContainer } from "@/components/ui/Toast";
import { useToast } from "@/hooks/useToast";
import { isTabRoot } from "@/lib/navRoots";

const EXIT_CONFIRM_MS = 2000;

/**
 * WS-4 (#114): Android hardware back-button behavior. A Capacitor WebView gets NO back handling by
 * default. This is native-only (web keeps stock browser back). Branches:
 *   (a) a stacked screen with real history (story, settings sub-screen)  → router.back()  (pop)
 *   (b) a NON-home tab root (Discover/Saved/Search/Following/Profile)     → router.replace("/")  (one hop to Today)
 *   (c) home (Today), OR any empty-history route (deep link / cold start) → toast "Press back again
 *       to exit", second press within 2s → App.minimizeApp(). Never App.exitApp().
 * The listener reads the CURRENT path via a ref, so it registers once (no re-subscribe per nav).
 */
export function BackButtonHandler() {
  const router = useRouter();
  const pathname = usePathname();
  const { toasts, addToast, removeToast } = useToast();
  const pathRef = useRef(pathname);
  pathRef.current = pathname;
  const confirmExitRef = useRef(false);
  const exitTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // The exit-confirm is a gesture on ONE screen: two CONSECUTIVE back presses. Any navigation in
  // between (a pop, a tab hop, a push) disarms it — otherwise the flag would leak across routes and a
  // later single press on home would minimize with no confirmation (WS-4 review).
  useEffect(() => {
    confirmExitRef.current = false;
    if (exitTimerRef.current) {
      clearTimeout(exitTimerRef.current);
      exitTimerRef.current = null;
    }
  }, [pathname]);

  useEffect(() => {
    if (!Capacitor.isNativePlatform()) return; // web: stock browser back semantics

    let remove: (() => void) | undefined;
    import("@capacitor/app").then(({ App }) => {
      App.addListener("backButton", ({ canGoBack }) => {
        const path = pathRef.current;
        const root = isTabRoot(path);

        if (!root && canGoBack) {
          router.back(); // (a) pop a stacked screen
          return;
        }
        if (root && path !== "/") {
          router.replace("/"); // (b) non-home tab root → one hop to Today
          return;
        }
        // (c) home, or empty-history anywhere → confirm-then-minimize (never exit)
        if (confirmExitRef.current) {
          confirmExitRef.current = false;
          void App.minimizeApp(); // keep state; NEVER exitApp()
          return;
        }
        confirmExitRef.current = true;
        addToast("Press back again to exit", "info");
        if (exitTimerRef.current) clearTimeout(exitTimerRef.current);
        exitTimerRef.current = setTimeout(() => {
          confirmExitRef.current = false;
          exitTimerRef.current = null;
        }, EXIT_CONFIRM_MS);
      }).then((sub) => {
        remove = () => sub.remove();
      });
    });

    return () => remove?.();
  }, [router, addToast]);

  return <ToastContainer toasts={toasts} onRemove={removeToast} />;
}
