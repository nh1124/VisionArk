"use client";

import React, { createContext, useContext, useState, useCallback, ReactNode } from "react";

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
}

const NotificationContext = createContext<NotificationContextType | undefined>(undefined);

export function NotificationProvider({ children }: { children: ReactNode }) {
    const [toasts, setToasts] = useState<Toast[]>([]);
    const [confirmDialog, setConfirmDialog] = useState<NotificationContextType["confirmDialog"]>(null);

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

    return (
        <NotificationContext.Provider
            value={{
                toasts,
                confirmDialog,
                showToast,
                showConfirm,
                closeConfirm,
                removeToast,
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
