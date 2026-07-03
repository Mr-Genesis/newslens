import type { Metadata } from "next";
import { Fraunces, DM_Sans, JetBrains_Mono } from "next/font/google";
import { NavBar } from "@/components/layout/NavBar";
import { BottomTabBar } from "@/components/layout/BottomTabBar";
import { ThemeProvider } from "@/components/ThemeProvider";
import { AuthProvider } from "@/components/AuthProvider";
import { SplashScreen } from "@/components/SplashScreen";
import { BackButtonHandler } from "@/components/BackButtonHandler";
import "./globals.css";

// Inline script to prevent flash of wrong theme (runs before React hydration)
const themeScript = `(function(){try{var t=localStorage.getItem("newslens-theme");if(t==="light")document.documentElement.classList.add("light");else if(t==="auto"&&window.matchMedia("(prefers-color-scheme: light)").matches)document.documentElement.classList.add("light")}catch(e){}})();`;

const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  style: ["normal", "italic"],
});

const dmSans = DM_Sans({
  variable: "--font-dm-sans",
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "NewsLens",
  description:
    "AI-powered news intelligence — daily briefings, swipable discovery, multi-source deep dives",
  // Static file in public/ (NOT an app/manifest.ts metadata route): the route-handler form breaks
  // Next 16's static export ("Failed to collect page data for /manifest.webmanifest"), which the
  // Capacitor build requires. The explicit link keeps <link rel="manifest"> emitted in both modes.
  manifest: "/manifest.webmanifest",
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  viewportFit: "cover" as const,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${fraunces.variable} ${dmSans.variable} ${jetbrainsMono.variable} antialiased`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="min-h-[100dvh] flex flex-col overflow-x-hidden">
        <ThemeProvider>
          <AuthProvider>
            <BackButtonHandler />
            <SplashScreen />
            <NavBar />
            <main className="flex-1 pt-[var(--page-top)] pb-[var(--page-bottom)]">
              {children}
            </main>
            <BottomTabBar />
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
