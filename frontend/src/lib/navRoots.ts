// WS-4 (#114): the root set that drives Android hardware-back behavior. A back press AT one of these
// roots hops to Today (non-home) or double-press-exits (home); any non-root route with real history
// just pops. Shared by BackButtonHandler and BottomTabBar so the two can't drift.
// Note: /following is a root for BACK purposes (hop to Today) even though it isn't a bottom tab.
export const TAB_ROOTS: ReadonlySet<string> = new Set([
  "/",
  "/discover",
  "/search",
  "/saved",
  "/following",
  "/settings",
]);

export function isTabRoot(pathname: string): boolean {
  return TAB_ROOTS.has(pathname);
}
