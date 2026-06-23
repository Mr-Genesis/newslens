import { LoadingScreen } from "@/components/ui/LoadingScreen";

/**
 * Route-level load screen. App Router renders this as the Suspense fallback
 * while a route segment resolves, giving navigation instant branded feedback.
 */
export default function Loading() {
  return <LoadingScreen />;
}
