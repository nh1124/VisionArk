"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { apiJson } from "@/lib/api";

function LinkContent() {
    const searchParams = useSearchParams();
    const router = useRouter();
    const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
    const [message, setMessage] = useState("");
    const [profile, setProfile] = useState<{ id: string } | null>(null);

    const token = searchParams.get("token");

    useEffect(() => {
        // 1. Fetch profile to ensure logged in
        apiJson<any>("/api/settings")
            .then(data => setProfile(data.profile))
            .catch(() => {
                setStatus("error");
                setMessage("Please log in to VisionArk first.");
            });
    }, []);

    const handleLink = async () => {
        if (!token || !profile) return;

        setStatus("loading");
        try {
            await apiJson("/api/line/link", {
                method: "POST",
                body: JSON.stringify({ token, user_id: profile.id })
            });
            setStatus("success");
            setMessage("LINE account linked successfully! You can now close this window or return to settings.");
            setTimeout(() => router.push("/settings"), 3000);
        } catch (err: any) {
            setStatus("error");
            setMessage(err.message || "Failed to link LINE account. The link may have expired.");
        }
    };

    if (!token) {
        return (
            <div className="text-center p-8 bg-gray-900 border border-gray-800 rounded-2xl max-w-md mx-auto mt-20">
                <h1 className="text-2xl font-bold mb-4">Invalid Link</h1>
                <p className="text-gray-400">This page requires a valid linking token from LINE.</p>
            </div>
        );
    }

    return (
        <div className="max-w-md mx-auto mt-20 p-8 bg-gray-900 border border-gray-800 rounded-3xl shadow-2xl animate-in fade-in zoom-in duration-300">
            <div className="flex justify-center mb-6">
                <div className="w-20 h-20 bg-green-600/20 rounded-3xl flex items-center justify-center text-4xl">
                    💬
                </div>
            </div>

            <h1 className="text-2xl font-extrabold text-center mb-2">Connect LINE</h1>
            <p className="text-gray-400 text-center text-sm mb-8">
                Confirm linking your LINE account to your VisionArk profile.
            </p>

            {status === "idle" && profile && (
                <button
                    onClick={handleLink}
                    className="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-4 rounded-2xl transition-all shadow-lg shadow-blue-900/20 active:scale-[0.98]"
                >
                    Link My Account
                </button>
            )}

            {status === "loading" && (
                <div className="flex flex-col items-center gap-4 py-4">
                    <div className="w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
                    <p className="text-blue-400 font-medium animate-pulse">Establishing Connection...</p>
                </div>
            )}

            {status === "success" && (
                <div className="p-4 bg-green-500/10 border border-green-500/50 rounded-2xl text-center">
                    <p className="text-green-400 font-bold mb-1">Success! 🎉</p>
                    <p className="text-xs text-green-500/80">{message}</p>
                </div>
            )}

            {status === "error" && (
                <div className="space-y-4">
                    <div className="p-4 bg-red-500/10 border border-red-500/50 rounded-2xl text-center">
                        <p className="text-red-400 font-bold mb-1">Linking Failed</p>
                        <p className="text-xs text-red-500/80">{message}</p>
                    </div>
                    {!profile && (
                        <button
                            onClick={() => router.push("/auth/login")}
                            className="w-full bg-gray-800 hover:bg-gray-700 text-white font-bold py-3 rounded-2xl transition-all"
                        >
                            Go to Login
                        </button>
                    )}
                </div>
            )}
        </div>
    );
}

export default function LineLinkPage() {
    return (
        <Suspense fallback={<div className="p-8 text-center text-gray-500">Loading...</div>}>
            <LinkContent />
        </Suspense>
    );
}
