"use client";

import { useAuth } from "@/lib/AuthContext";
import { useRouter, usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import Sidebar from "@/components/Sidebar";
import Navbar from "@/components/Navbar";

interface AuthGuardProps {
    children: React.ReactNode;
}

export default function AuthGuard({ children }: AuthGuardProps) {
    const { isAuthenticated, isLoading, logout } = useAuth();
    const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

    useEffect(() => {
        const saved = localStorage.getItem("sidebar-collapsed");
        setSidebarCollapsed(saved === "true");
    }, []);

    const toggleSidebar = () => {
        const newState = !sidebarCollapsed;
        setSidebarCollapsed(newState);
        localStorage.setItem("sidebar-collapsed", newState.toString());
    };

    const router = useRouter();
    const pathname = usePathname();

    // Skip guard for auth pages
    const isAuthPage = pathname?.startsWith("/auth");

    useEffect(() => {
        if (!isLoading && !isAuthenticated && !isAuthPage) {
            router.push("/auth/signin");
        }
    }, [isAuthenticated, isLoading, isAuthPage, router]);

    // Loading state
    if (isLoading) {
        return (
            <div className="min-h-screen bg-gray-950 flex items-center justify-center text-white">
                <div className="text-center">
                    <div className="inline-flex items-center justify-center w-16 h-16 bg-gradient-to-br from-blue-500 to-purple-600 rounded-2xl mb-4 animate-pulse shadow-[0_0_20px_rgba(37,99,235,0.3)]">
                        <span className="text-3xl text-white">🧠</span>
                    </div>
                    <p className="text-gray-400 font-medium">Initializing Vision Ark...</p>
                </div>
            </div>
        );
    }

    // Auth pages render without sidebar
    if (isAuthPage) {
        return <>{children}</>;
    }

    // Protected pages - show sidebar if authenticated
    if (!isAuthenticated) {
        return null; // Will redirect
    }

    return (
        <div className="flex h-screen overflow-hidden bg-gray-950">
            {/* Sidebar is the master vertical anchor on the left */}
            <Sidebar isCollapsed={sidebarCollapsed} onToggle={toggleSidebar} />

            {/* Content area is a vertical stack on the right */}
            <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
                <Navbar isSidebarCollapsed={sidebarCollapsed} />
                <main className="flex-1 relative flex flex-col min-w-0 overflow-y-auto">
                    {children}
                </main>
            </div>
        </div>
    );
}
