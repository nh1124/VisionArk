"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import MobileSidebar from "./MobileSidebar";
import BottomNav from "./BottomNav";
import { NotificationBell } from "../NotificationBell";
import { useMobileSwipe } from "@/hooks/useMobileSwipe";
import { Files, StickyNote, Activity as ActivityIcon } from "lucide-react";

interface MobileLayoutProps {
    children: React.ReactNode;
}

export default function MobileLayout({ children }: MobileLayoutProps) {
    const [isSidebarOpen, setIsSidebarOpen] = useState(false);
    const [isUIHidden, setIsUIHidden] = useState(false);
    const pathname = usePathname();

    // Enable swipe right to open sidebar
    useMobileSwipe({
        onSwipeRight: () => setIsSidebarOpen(true),
        onSwipeLeft: () => setIsSidebarOpen(false)
    });

    const getPageTitle = () => {
        if (pathname === "/dashboard") return "Dashboard";
        if (pathname === "/tasks") return "Tasks";
        if (pathname.startsWith("/projects")) return "Projects";
        if (pathname === "/settings") return "Settings";
        return "Vision Ark";
    };

    React.useEffect(() => {
        const handleToggle = (e: any) => setIsUIHidden(e.detail.hidden);
        window.addEventListener('toggle-ui-visibility', handleToggle);
        return () => window.removeEventListener('toggle-ui-visibility', handleToggle);
    }, []);

    return (
        <div className="flex flex-col relative h-[100dvh] w-full bg-gray-950 overflow-hidden">
            {/* Mobile Sidebar Overlay */}
            <MobileSidebar
                isOpen={isSidebarOpen}
                onClose={() => setIsSidebarOpen(false)}
            />

            {/* Mobile Header: Simple & Focused */}
            <header className={`absolute top-0 w-full h-14 border-b border-gray-800 flex items-center justify-between px-4 bg-gray-950/80 backdrop-blur-xl z-30 transition-transform duration-300 ease-in-out ${isUIHidden ? "-translate-y-full" : "translate-y-0"}`}>
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

                <div className="flex items-center gap-1">
                    {pathname.startsWith("/projects/") && pathname.split("/").length >= 3 && (
                        <div className="flex items-center mr-1">
                            <button
                                onClick={() => window.dispatchEvent(new CustomEvent('toggle-project-sidebar', { detail: { mode: 'files' } }))}
                                className="p-2 text-gray-400 hover:text-cyan-400 transition-colors"
                                title="Artifacts"
                            >
                                <Files size={18} />
                            </button>
                            <button
                                onClick={() => window.dispatchEvent(new CustomEvent('toggle-project-sidebar', { detail: { mode: 'notes' } }))}
                                className="p-2 text-gray-400 hover:text-cyan-400 transition-colors"
                                title="Notes"
                            >
                                <StickyNote size={18} />
                            </button>
                            <button
                                onClick={() => window.dispatchEvent(new CustomEvent('toggle-project-sidebar', { detail: { mode: 'activity' } }))}
                                className="p-2 text-gray-400 hover:text-cyan-400 transition-colors"
                                title="Activity"
                            >
                                <ActivityIcon size={18} />
                            </button>
                        </div>
                    )}
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

            {/* Content Area: Full Width, Allows Overlays */}
            <main className="flex-1 w-full h-full relative flex flex-col min-w-0 overflow-y-auto">
                {children}
            </main>

            {/* Mobile Bottom Navigation */}
            <div className={`absolute bottom-0 w-full z-30 transition-transform duration-300 ease-in-out ${isUIHidden ? "translate-y-full" : "translate-y-0"}`}>
                <BottomNav />
            </div>

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
