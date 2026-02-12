"use client";

import { useEffect, useRef } from "react";

interface SwipeOptions {
    onSwipeRight?: () => void;
    onSwipeLeft?: () => void;
    threshold?: number;
}

/**
 * Hook to detect swipe gestures for mobile navigation.
 * Useful for opening/closing sidebars.
 */
export function useMobileSwipe({ onSwipeRight, onSwipeLeft, threshold = 100 }: SwipeOptions) {
    const touchStart = useRef<number | null>(null);
    const touchEnd = useRef<number | null>(null);

    useEffect(() => {
        const handleTouchStart = (e: TouchEvent) => {
            touchStart.current = e.targetTouches[0].clientX;
        };

        const handleTouchMove = (e: TouchEvent) => {
            touchEnd.current = e.targetTouches[0].clientX;
        };

        const handleTouchEnd = () => {
            if (!touchStart.current || !touchEnd.current) return;

            const distance = touchStart.current - touchEnd.current;
            const isLeftSwipe = distance > threshold;
            const isRightSwipe = distance < -threshold;

            if (isLeftSwipe && onSwipeLeft) {
                onSwipeLeft();
            } else if (isRightSwipe && onSwipeRight) {
                onSwipeRight();
            }

            // Reset
            touchStart.current = null;
            touchEnd.current = null;
        };

        window.addEventListener("touchstart", handleTouchStart);
        window.addEventListener("touchmove", handleTouchMove);
        window.addEventListener("touchend", handleTouchEnd);

        return () => {
            window.removeEventListener("touchstart", handleTouchStart);
            window.removeEventListener("touchmove", handleTouchMove);
            window.removeEventListener("touchend", handleTouchEnd);
        };
    }, [onSwipeLeft, onSwipeRight, threshold]);
}
