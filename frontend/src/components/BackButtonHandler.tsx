"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Capacitor } from "@capacitor/core";

/** Bottom-tab roots: hardware back from any of these minimizes the app instead of navigating. */
const ROOTS = new Set(["/", "/discover", "/search", "/saved", "/following", "/settings"]);

/**
 * Android hardware back support. A Capacitor WebView receives NO back-button behavior by
 * default — without this listener the system back button does nothing (device-QA #5).
 * In-app history → router.back(); at a tab root (or no history) → minimize, never exit.
 */
export function BackButtonHandler() {
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!Capacitor.isNativePlatform()) return;

    let remove: (() => void) | undefined;
    import("@capacitor/app").then(({ App }) => {
      App.addListener("backButton", ({ canGoBack }) => {
        if (!ROOTS.has(pathname) && canGoBack) {
          router.back();
        } else {
          App.minimizeApp(); // keep state; never exitApp()
        }
      }).then((sub) => {
        remove = () => sub.remove();
      });
    });
    return () => remove?.();
  }, [pathname, router]);

  return null;
}
