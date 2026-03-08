"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Settings } from "lucide-react";
import { NotificationBell } from "./NotificationBell";

export default function Navbar() {
    const pathname = usePathname();

    // Don't show navbar on auth pages or chat pages (Hub/Spoke)
    if (pathname.startsWith("/auth")) return null;
    if (pathname === "/hub") return null;
    if (pathname.match(/^\/spokes\/[^\/]+$/)) return null;

    return (
        <nav className="bg-gray-950 border-b border-gray-800 px-6 py-2.5 flex items-center justify-between flex-shrink-0">
            <div className="flex items-center space-x-4">
                <div className="flex items-center space-x-2">
                    <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse shadow-[0_0_8px_rgba(59,130,246,0.5)]"></div>
                    <span className="text-[10px] font-black uppercase tracking-[0.3em] text-gray-500">
                        Vision Ark
                    </span>
                </div>
            </div>

            <div className="flex items-center space-x-2">
                <NotificationBell />

                <Link
                    href="/settings"
                    className={`p-2 rounded-lg transition-colors ${pathname === "/settings" ? "bg-cyan-500/20 text-cyan-400" : "text-gray-400 hover:text-white hover:bg-gray-800"}`}
                    title="Settings"
                >
                    <Settings size={18} />
                </Link>
            </div>
        </nav>
    );
}
