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

    // Redirect to dashboard if authenticated and on root page
    useEffect(() => {
        if (isAuthenticated && pathname === "/") {
            router.push("/dashboard");
        }
    }, [isAuthenticated, pathname, router]);

    // Loading state
    if (isLoading || isMobile === null) {
        return (
            <div className="min-h-screen bg-gray-950 flex items-center justify-center text-white">
                <div className="relative mb-6">
                    <img
                        src="/icon-512x512.png"
                        alt="VisionArk Logo"
                        className="w-20 h-20 rounded-2xl shadow-[0_0_30px_rgba(37,99,235,0.2)] animate-pulse"
                    />
                </div>
                <p className="text-gray-400 font-medium">Initializing Vision Ark...</p>
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
