"use client";

import React, { createContext, useContext, useState, useCallback, ReactNode, useEffect, useRef } from "react";
import { useAuth } from "./AuthContext";

type NotificationType = "success" | "error" | "info" | "warning";

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
}

const NotificationContext = createContext<NotificationContextType | undefined>(undefined);

export function NotificationProvider({ children }: { children: ReactNode }) {
    const { userId, isAuthenticated } = useAuth();
    const [toasts, setToasts] = useState<Toast[]>([]);
    const [confirmDialog, setConfirmDialog] = useState<NotificationContextType["confirmDialog"]>(null);
    const [unreadCount, setUnreadCount] = useState(0);
    const wsRef = useRef<WebSocket | null>(null);

    const showToast = useCallback((message: string, type: NotificationType = "info") => {
        const id = Math.random().toString(36).substring(2, 9);
        setToasts((prev) => [...prev, { id, message, type }]);

        // Auto remove after 5 seconds
        setTimeout(() => {
            setToasts((prev) => prev.filter((t) => t.id !== id));
        }, 5000);
    }, []);

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
            // Determine WS URL - in local dev we often need to point to 8000 directly
            // because Next.js dev server proxying for WS is tricky.
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
                    console.error("Failed to parse WebSocket message:", err);
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
        refreshUnreadCount();

        return () => {
            if (wsRef.current) {
                wsRef.current.close();
                wsRef.current = null;
            }
            clearTimeout(reconnectTimer);
        };
    }, [isAuthenticated, userId, showToast, refreshUnreadCount]);

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
