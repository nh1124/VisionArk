"use client";

import Link from "next/link";
import { useAuth } from "@/lib/AuthContext";
import { usePathname } from "next/navigation";
import SystemStatus from "./SystemStatus";

interface NavbarProps {
    isSidebarCollapsed: boolean;
}

export default function Navbar({ isSidebarCollapsed }: NavbarProps) {
    const { username, logout } = useAuth();
    const pathname = usePathname();

    // Don't show navbar on auth pages
    if (pathname.startsWith("/auth")) return null;

    return (
        <nav className="bg-gray-950 border-b border-gray-800 px-6 py-3 flex items-center justify-between flex-shrink-0">
            <div className="flex items-center space-x-8">
                {/* Contextual indicator instead of branding - hide when sidebar is open (not collapsed) */}
                {isSidebarCollapsed && (
                    <div className="flex items-center space-x-2">
                        <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse shadow-[0_0_8px_rgba(59,130,246,0.5)]"></div>
                        <span className="text-[10px] font-black uppercase tracking-[0.3em] text-gray-500">
                            Vision Ark
                        </span>
                    </div>
                )}

                <div className="hidden md:flex items-center space-x-6 text-sm font-medium text-gray-400">
                    <Link
                        href="/dashboard"
                        className={`hover:text-white transition-colors ${pathname === "/dashboard" ? "text-blue-400" : ""}`}
                    >
                        Dashboard
                    </Link>
                    <Link
                        href="/hub"
                        className={`hover:text-white transition-colors ${pathname === "/hub" ? "text-purple-400" : ""}`}
                    >
                        Hub
                    </Link>
                    <Link
                        href="/inbox"
                        className={`hover:text-white transition-colors ${pathname === "/inbox" ? "text-green-400" : ""}`}
                    >
                        Inbox
                    </Link>
                    <Link
                        href="/spokes"
                        className={`hover:text-white transition-colors ${pathname.startsWith("/spokes") ? "text-cyan-400" : ""}`}
                    >
                        Spokes
                    </Link>
                </div>
            </div>

            <div className="flex items-center space-x-4">
                <SystemStatus />

                <div className="flex items-center space-x-2 text-sm text-gray-400 bg-gray-900 px-3 py-1.5 rounded-full border border-gray-800">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                    </svg>
                    <span className="font-medium text-gray-200">{username || "User"}</span>
                </div>

                <Link
                    href="/settings"
                    className={`p-2 rounded-lg hover:bg-gray-800 transition-colors ${pathname === "/settings" ? "text-blue-400 bg-gray-900" : "text-gray-400"}`}
                    title="Settings"
                >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37a1.724 1.724 0 002.572-1.065z" />
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                </Link>

                <button
                    onClick={logout}
                    className="p-2 text-gray-400 hover:text-red-400 hover:bg-red-400/10 rounded-lg transition-colors"
                    title="Logout"
                >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                    </svg>
                </button>
            </div>
        </nav>
    );
}
