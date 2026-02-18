"use client";

import { Inter, Outfit } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const outfit = Outfit({ subsets: ["latin"], variable: "--font-outfit" });

export default function GlobalError({
    error,
    reset,
}: {
    error: Error & { digest?: string };
    reset: () => void;
}) {
    console.error("Global Error:", error);

    return (
        <html lang="en" className="dark h-full">
            <body className={`${inter.variable} ${outfit.variable} font-sans bg-gray-950 text-gray-100 h-full flex flex-col items-center justify-center`}>
                <div className="w-full max-w-md px-8 text-center">
                    <div className="mb-6 inline-flex h-20 w-20 items-center justify-center rounded-2xl bg-red-500/10 shadow-xl shadow-red-900/10 border border-red-500/20">
                        <span className="text-4xl text-red-500">💥</span>
                    </div>
                    <h2 className="mb-3 text-2xl font-bold text-red-400">Critical System Error</h2>
                    <p className="mb-2 text-gray-400 font-mono text-xs bg-gray-900 p-3 rounded-lg border border-gray-800 break-all">
                        {error.message || "A critical error occurred in the root layout."}
                    </p>
                    <button
                        onClick={() => reset()}
                        className="inline-flex w-full items-center justify-center rounded-xl bg-red-600 px-6 py-3 font-semibold text-white transition-all hover:bg-red-500 active:scale-95 shadow-lg shadow-red-900/20"
                    >
                        Reload Application
                    </button>
                </div>
            </body>
        </html>
    );
}
