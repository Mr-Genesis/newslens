import type { NextConfig } from "next";

const isCapacitor = process.env.BUILD_TARGET === "capacitor";

const nextConfig: NextConfig = {
  // Static export for Capacitor (Android/iOS) builds
  ...(isCapacitor ? { output: "export" } : {}),

  // Proxy API calls to FastAPI backend — no CORS needed (web only)
  ...(!isCapacitor
    ? {
        async rewrites() {
          return [
            {
              source: "/api/:path*",
              destination: "http://localhost:8000/:path*",
            },
          ];
        },
      }
    : {}),
};

export default nextConfig;
