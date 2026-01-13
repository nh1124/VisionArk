"use client";

import { useState, useEffect } from "react";

/**
 * Custom hook to detect if the current device is mobile based on window width.
 * Handles SSR correctly by initializing with null and updating after mount.
 */
export function useIsMobile(threshold: number = 768) {
    const [isMobile, setIsMobile] = useState<boolean | null>(null);

    useEffect(() => {
        const checkMobile = () => {
            setIsMobile(window.innerWidth < threshold);
        };

        // Initial check
        checkMobile();

        // Add event listener
        window.addEventListener("resize", checkMobile);

        // Cleanup
        return () => window.removeEventListener("resize", checkMobile);
    }, [threshold]);

    return isMobile;
}
