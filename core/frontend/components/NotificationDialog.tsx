"use client";

import React from "react";
import { useNotification } from "@/lib/NotificationContext";
import { X, AlertTriangle, Info, CheckCircle2, AlertCircle } from "lucide-react";

export function NotificationDialog() {
    const { confirmDialog, closeConfirm } = useNotification();

    if (!confirmDialog || !confirmDialog.isOpen) return null;

    const { message, options } = confirmDialog;
    const { title = "Confirmation", confirmText = "Confirm", cancelText = "Cancel", variant = "primary" } = options;

    const getIcon = () => {
        switch (variant) {
            case "danger": return <AlertTriangle className="text-red-500" size={24} />;
            case "warning": return <AlertCircle className="text-yellow-500" size={24} />;
            default: return <Info className="text-cyan-500" size={24} />;
        }
    };

    const getConfirmButtonStyles = () => {
        switch (variant) {
            case "danger": return "bg-red-600 hover:bg-red-500 shadow-red-900/20";
            case "warning": return "bg-yellow-600 hover:bg-yellow-500 shadow-yellow-900/20";
            default: return "bg-cyan-600 hover:bg-cyan-500 shadow-cyan-900/20";
        }
    };

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
            <div
                className="w-full max-w-md bg-gray-900 border border-gray-800 rounded-3xl shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200"
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header-like top bar */}
                <div className="h-1 w-full bg-gradient-to-r from-transparent via-cyan-500/50 to-transparent"></div>

                <div className="p-8">
                    <div className="flex items-center gap-4 mb-6">
                        <div className="p-3 bg-gray-800/50 rounded-2xl border border-gray-700/50 shadow-inner">
                            {getIcon()}
                        </div>
                        <h3 className="text-xl font-bold text-gray-100">{title}</h3>
                    </div>

                    <p className="text-gray-400 text-sm leading-relaxed mb-8">
                        {message}
                    </p>

                    <div className="flex gap-4">
                        <button
                            onClick={() => closeConfirm(false)}
                            className="flex-1 px-6 py-3 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-2xl font-semibold text-sm transition-all active:scale-95 border border-gray-700/50"
                        >
                            {cancelText}
                        </button>
                        <button
                            onClick={() => closeConfirm(true)}
                            className={`flex-1 px-6 py-3 text-white rounded-2xl font-semibold text-sm transition-all active:scale-95 shadow-lg ${getConfirmButtonStyles()}`}
                        >
                            {confirmText}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}

export function ToastNotification() {
    const { toasts, removeToast } = useNotification();

    return (
        <div className="fixed bottom-8 right-8 z-[100] flex flex-col gap-3 pointer-events-none">
            {toasts.map((toast) => (
                <div
                    key={toast.id}
                    className="group pointer-events-auto flex items-center gap-3 bg-gray-900/90 backdrop-blur-md border border-gray-800 rounded-2xl px-5 py-4 shadow-2xl animate-in slide-in-from-right-10 fade-in duration-300 min-w-[300px] max-w-md"
                >
                    <div className="flex-shrink-0">
                        {toast.type === "success" && <CheckCircle2 className="text-green-500" size={20} />}
                        {toast.type === "error" && <AlertCircle className="text-red-500" size={20} />}
                        {toast.type === "warning" && <AlertTriangle className="text-yellow-500" size={20} />}
                        {toast.type === "info" && <Info className="text-cyan-500" size={20} />}
                    </div>

                    <div className="flex-1 text-sm font-medium text-gray-200">
                        {toast.message}
                    </div>

                    <button
                        onClick={() => removeToast(toast.id)}
                        className="text-gray-500 hover:text-white p-1 rounded-lg transition-colors"
                    >
                        <X size={16} />
                    </button>

                    {/* Progress bar at bottom */}
                    <div className="absolute bottom-0 left-0 h-0.5 bg-gray-700/50 w-full overflow-hidden rounded-b-2xl">
                        <div
                            className={`h-full animate-toast-progress ${toast.type === "success" ? "bg-green-500" :
                                    toast.type === "error" ? "bg-red-500" :
                                        toast.type === "warning" ? "bg-yellow-500" :
                                            "bg-cyan-500"
                                }`}
                            style={{ animationDuration: '5s', animationTimingFunction: 'linear' }}
                        ></div>
                    </div>
                </div>
            ))}
        </div>
    );
}
