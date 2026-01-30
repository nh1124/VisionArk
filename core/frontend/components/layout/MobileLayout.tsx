"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import MobileSidebar from "./MobileSidebar";
import { NotificationBell } from "../NotificationBell";

interface MobileLayoutProps {
    children: React.ReactNode;
}

export default function MobileLayout({ children }: MobileLayoutProps) {
    const [isSidebarOpen, setIsSidebarOpen] = useState(false);
    const pathname = usePathname();

    const getPageTitle = () => {
        if (pathname === "/dashboard") return "Dashboard";
        if (pathname === "/tasks") return "Tasks";
        if (pathname.startsWith("/projects")) return "Projects";
        if (pathname === "/settings") return "Settings";
        return "Vision Ark";
    };

    return (
        <div className="flex flex-col h-[100dvh] w-full bg-gray-950 overflow-hidden">
            {/* Mobile Sidebar Overlay */}
            <MobileSidebar
                isOpen={isSidebarOpen}
                onClose={() => setIsSidebarOpen(false)}
            />

            {/* Mobile Header: Simple & Focused */}
            <header className="h-14 border-b border-gray-800 flex items-center justify-between px-4 bg-gray-950/80 backdrop-blur-xl z-20 flex-shrink-0">
                <div className="flex items-center gap-3">
                    <Link href="/" className="flex items-center gap-2">
                        <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center font-bold text-white text-sm shadow-[0_0_15px_rgba(37,99,235,0.3)]">
                            V
                        </div>
                    </Link>
                    <h1 className="text-sm font-bold text-gray-200 tracking-tight">
                        {getPageTitle()}
                    </h1>
                </div>

                <div className="flex items-center gap-2">
                    <NotificationBell />
                    <button
                        onClick={() => setIsSidebarOpen(true)}
                        className="p-2 text-gray-400 hover:text-white transition-colors"
                    >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                        </svg>
                    </button>
                </div>
            </header>

            {/* Content Area: Single Column, 100% Width */}
            <main className="flex-1 relative flex flex-col min-w-0 overflow-y-auto">
                {children}
            </main>

            {/* Mobile-specific global overrides */}
            <style jsx global>{`
                /* Ensure better touch targets on mobile */
                button, a {
                    min-height: 44px;
                    min-width: 44px;
                }
                /* Smooth momentum scrolling for iOS */
                .scrolling-touch {
                    -webkit-overflow-scrolling: touch;
                }
                /* Dynamic viewport height for mobile browsers */
                .h-screen-dvh {
                    height: 100dvh;
                }
            `}</style>
        </div>
    );
}
