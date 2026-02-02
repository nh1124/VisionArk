"use client";

import React, { createContext, useContext, useState, useCallback, ReactNode, useEffect, useRef } from "react";
import { useAuth } from "./AuthContext";

type NotificationType = "success" | "error" | "info" | "warning" | "timer";

interface Toast {
    id: string;
    message: string;
    type: NotificationType;
}

interface ConfirmOptions {
    title?: string;
    confirmText?: string;
    cancelText?: string;
    variant?: "danger" | "primary" | "warning";
}

interface NotificationContextType {
    toasts: Toast[];
    confirmDialog: {
        isOpen: boolean;
        message: string;
        options: ConfirmOptions;
        resolve: (value: boolean) => void;
    } | null;
    showToast: (message: string, type?: NotificationType) => void;
    showConfirm: (message: string, options?: ConfirmOptions) => Promise<boolean>;
    closeConfirm: (result: boolean) => void;
    removeToast: (id: string) => void;
    unreadCount: number;
    refreshUnreadCount: () => Promise<void>;
    refreshSettings: () => Promise<void>;
}

const NotificationContext = createContext<NotificationContextType | undefined>(undefined);

export function NotificationProvider({ children }: { children: ReactNode }) {
    const { userId, isAuthenticated } = useAuth();
    const [toasts, setToasts] = useState<Toast[]>([]);
    const [confirmDialog, setConfirmDialog] = useState<NotificationContextType["confirmDialog"]>(null);
    const [unreadCount, setUnreadCount] = useState(0);
    const [settings, setSettings] = useState<any>(null);
    const settingsRef = useRef<any>(null);
    const wsRef = useRef<WebSocket | null>(null);

    // Sync settingsRef with settings state
    useEffect(() => {
        settingsRef.current = settings;
    }, [settings]);

    const refreshSettings = useCallback(async () => {
        if (!isAuthenticated) return;
        try {
            const token = localStorage.getItem("atmos_access_token");
            const res = await fetch("/api/settings", {
                headers: { "Authorization": `Bearer ${token}` }
            });
            if (res.ok) {
                const data = await res.json();
                setSettings(data);
            }
        } catch (err) {
            console.error("[NotificationContext] Failed to fetch settings:", err);
        }
    }, [isAuthenticated]);

    const playNotificationSound = useCallback((type: NotificationType) => {
        console.log("[NotificationContext] playNotificationSound called with type:", type);
        if (type !== "timer") return;

        try {
            const currentSettings = settingsRef.current;
            const sound = currentSettings?.general_settings?.notification_sound || "timer";
            console.log(`[NotificationContext] Attempting to play sound: ${sound}`);
            const audio = new Audio(`/assets/sounds/${sound}.mp3`);
            audio.volume = 0.5;
            audio.play()
                .then(() => console.log("[NotificationContext] Sound played successfully"))
                .catch(err => {
                    console.warn("[NotificationContext] Audio play blocked or failed:", err);
                });
        } catch (err) {
            console.error("[NotificationContext] Failed to play sound:", err);
        }
    }, []); // Stabilized: no dependencies

    const showToast = useCallback((message: string, type: NotificationType = "info") => {
        const id = Math.random().toString(36).substring(2, 9);
        setToasts((prev) => [...prev, { id, message, type }]);
        playNotificationSound(type);
        setTimeout(() => {
            setToasts((prev) => prev.filter((t) => t.id !== id));
        }, 5000);
    }, [playNotificationSound]);

    const removeToast = useCallback((id: string) => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
    }, []);

    const showConfirm = useCallback((message: string, options: ConfirmOptions = {}) => {
        return new Promise<boolean>((resolve) => {
            setConfirmDialog({
                isOpen: true,
                message,
                options,
                resolve,
            });
        });
    }, []);

    const closeConfirm = useCallback((result: boolean) => {
        if (confirmDialog) {
            confirmDialog.resolve(result);
            setConfirmDialog(null);
        }
    }, [confirmDialog]);

    const refreshUnreadCount = useCallback(async () => {
        if (!isAuthenticated) return;
        try {
            const token = localStorage.getItem("atmos_access_token");
            const res = await fetch("/api/notifications", {
                headers: { "Authorization": `Bearer ${token}` }
            });
            if (res.ok) {
                const data = await res.json();
                setUnreadCount(data.unread_count);
            }
        } catch (err) {
            console.error("Failed to fetch unread count:", err);
        }
    }, [isAuthenticated]);

    // Data bootstrap effect
    useEffect(() => {
        if (isAuthenticated) {
            refreshUnreadCount();
            refreshSettings();
        }
    }, [isAuthenticated, userId, refreshUnreadCount, refreshSettings]);

    // WebSocket Integration
    useEffect(() => {
        if (!isAuthenticated || !userId) {
            if (wsRef.current) {
                wsRef.current.close();
                wsRef.current = null;
            }
            return;
        }

        let reconnectTimer: NodeJS.Timeout;

        const connect = () => {
            const isLocal = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
            const wsHost = isLocal ? "localhost:8000" : window.location.host;
            const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
            const wsUrl = `${protocol}//${wsHost}/api/notifications/ws/${userId}`;

            console.log(`[NotificationContext] Connecting to WebSocket: ${wsUrl}`);
            const ws = new WebSocket(wsUrl);
            wsRef.current = ws;

            ws.onmessage = (event) => {
                try {
                    const payload = JSON.parse(event.data);
                    if (payload.type === "notification") {
                        const notif = payload.data;
                        showToast(notif.title, notif.type as NotificationType);
                        setUnreadCount((prev) => prev + 1);
                    }
                } catch (err) {
                    console.error("[NotificationContext] Failed to parse WebSocket message:", err);
                }
            };

            ws.onclose = () => {
                console.log("Notifications WebSocket closed. Reconnecting in 5s...");
                reconnectTimer = setTimeout(() => {
                    if (isAuthenticated && userId) connect();
                }, 5000);
            };

            ws.onerror = (err) => {
                console.error("Notifications WebSocket error:", err);
                ws.close();
            };
        };

        connect();

        return () => {
            if (wsRef.current) {
                wsRef.current.close();
                wsRef.current = null;
            }
            clearTimeout(reconnectTimer);
        };
    }, [isAuthenticated, userId, showToast]);

    return (
        <NotificationContext.Provider
            value={{
                toasts,
                confirmDialog,
                showToast,
                showConfirm,
                closeConfirm,
                removeToast,
                unreadCount,
                refreshUnreadCount,
                refreshSettings,
            }}
        >
            {children}
        </NotificationContext.Provider>
    );
}

export function useNotification() {
    const context = useContext(NotificationContext);
    if (context === undefined) {
        throw new Error("useNotification must be used within a NotificationProvider");
    }
    return context;
}
