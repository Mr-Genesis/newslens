import type { Metadata } from "next";
import { Fraunces, DM_Sans, JetBrains_Mono } from "next/font/google";
import { NavBar } from "@/components/layout/NavBar";
import { BottomTabBar } from "@/components/layout/BottomTabBar";
import { ThemeProvider } from "@/components/ThemeProvider";
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
          <NavBar />
          <main className="flex-1 pt-[var(--page-top)] pb-[var(--page-bottom)]">
            {children}
          </main>
          <BottomTabBar />
        </ThemeProvider>
      </body>
    </html>
  );
}
