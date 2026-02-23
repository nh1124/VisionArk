import type { Metadata, Viewport } from "next";
import { Inter, Outfit } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/lib/AuthContext";
import { ModelProvider } from "@/lib/ModelContext";
import AuthGuard from "@/components/AuthGuard";
import Navbar from "@/components/Navbar";
import { NotificationProvider } from "@/lib/NotificationContext";
import { NotificationDialog, ToastNotification } from "@/components/NotificationDialog";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const outfit = Outfit({ subsets: ["latin"], variable: "--font-outfit" });

export const metadata: Metadata = {
  title: "Vision Ark",
  description: "Advanced AI Task Management OS",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "Vision Ark",
  },
};

export const viewport: Viewport = {
  themeColor: "#121212",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark h-full overflow-hidden" suppressHydrationWarning={true}>
      <body className={`${inter.variable} ${outfit.variable} font-sans bg-gray-950 text-gray-100 h-full relative overflow-hidden flex flex-col`} suppressHydrationWarning={true}>
        <AuthProvider>
          <NotificationProvider>
            <ModelProvider>
              <AuthGuard>
                {children}
              </AuthGuard>
            </ModelProvider>
            <NotificationDialog />
            <ToastNotification />
          </NotificationProvider>
        </AuthProvider>

        <script dangerouslySetInnerHTML={{
          __html: `
            if ('serviceWorker' in navigator) {
              window.addEventListener('load', function() {
                navigator.serviceWorker.register('/sw.js').then(function(registration) {
                  console.log('ServiceWorker registration successful with scope: ', registration.scope);
                }, function(err) {
                  console.log('ServiceWorker registration failed: ', err);
                });
              });
            }
          `
        }} />
      </body>
    </html>
  );
}

