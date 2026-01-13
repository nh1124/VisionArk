"use client";

import { useAuth } from "@/lib/AuthContext";
import { useRouter, usePathname } from "next/navigation";
import { useEffect } from "react";
import { useIsMobile } from "@/hooks/useIsMobile";
import DesktopLayout from "@/components/layout/DesktopLayout";
import MobileLayout from "@/components/layout/MobileLayout";

interface AuthGuardProps {
    children: React.ReactNode;
}

export default function AuthGuard({ children }: AuthGuardProps) {
    const { isAuthenticated, isLoading } = useAuth();
    const isMobile = useIsMobile();

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
    if (isLoading || isMobile === null) {
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

    // Protected pages - show layout if authenticated
    if (!isAuthenticated) {
        return null; // Will redirect
    }

    // Adaptive Switcher
    return isMobile ? (
        <MobileLayout>{children}</MobileLayout>
    ) : (
        <DesktopLayout>{children}</DesktopLayout>
    );
}
