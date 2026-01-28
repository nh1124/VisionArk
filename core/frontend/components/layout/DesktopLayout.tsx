"use client";

import React, { useState, useEffect } from "react";
import { usePathname } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import Navbar from "@/components/Navbar";
import FloatingAIManager from "@/components/FloatingAIManager";

interface DesktopLayoutProps {
    children: React.ReactNode;
}

export default function DesktopLayout({ children }: DesktopLayoutProps) {
    const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
    const pathname = usePathname();

    // Hide navbar on project chat pages
    const isProjectChatPage = pathname?.startsWith("/projects/") && pathname !== "/projects";

    useEffect(() => {
        const saved = localStorage.getItem("sidebar-collapsed");
        setSidebarCollapsed(saved === "true");
    }, []);

    const toggleSidebar = () => {
        const newState = !sidebarCollapsed;
        setSidebarCollapsed(newState);
        localStorage.setItem("sidebar-collapsed", newState.toString());
    };

    return (
        <div className="flex h-full overflow-hidden bg-gray-950">
            {/* Sidebar is the master vertical anchor on the left */}
            <Sidebar isCollapsed={sidebarCollapsed} onToggle={toggleSidebar} />

            {/* Content area is a vertical stack on the right */}
            <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
                {!isProjectChatPage && <Navbar isSidebarCollapsed={sidebarCollapsed} />}
                <main className={`flex-1 relative flex flex-col min-w-0 ${isProjectChatPage ? "overflow-hidden" : "overflow-y-auto"}`}>
                    {children}
                </main>
                {!isProjectChatPage && <FloatingAIManager />}
            </div>
        </div>
    );
}
