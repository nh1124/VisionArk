"use client";

import { useState } from "react";
import { useAuth } from "@/lib/AuthContext";
import Link from "next/link";

export default function SignUpPage() {
    const { login } = useAuth();
    const [formData, setFormData] = useState({
        username: "",
        email: "",
        password: "",
        confirmPassword: "",
        lbs_api_key: "",
        kc_api_key: "",
        gemini_api_key: "",
    });

    const isUsernameValid = formData.username.trim().length >= 3;
    const isPasswordValid = formData.password.length >= 8;
    const isConfirmValid = formData.password === formData.confirmPassword && formData.password !== "";
    const isFormValid = isUsernameValid && isPasswordValid && isConfirmValid && formData.lbs_api_key !== "" && formData.kc_api_key !== "" && formData.gemini_api_key !== "";
    const [testStatus, setTestStatus] = useState<{ type: "success" | "error" | "loading", message: string } | null>(null);
    const [kcTestStatus, setKcTestStatus] = useState<{ type: "success" | "error" | "loading", message: string } | null>(null);
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        setFormData((prev) => ({
            ...prev,
            [e.target.name]: e.target.value,
        }));
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError("");
        setLoading(true);

        if (!isFormValid) {
            setError("Please correct all errors and fill required fields before submitting.");
            setLoading(false);
            return;
        }

        try {
            const response = await fetch("/api/auth/register", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    username: formData.username,
                    email: formData.email || null,
                    password: formData.password,
                    lbs_api_key: formData.lbs_api_key,
                    kc_api_key: formData.kc_api_key,
                    gemini_api_key: formData.gemini_api_key,
                }),
            });

            const data = await response.json();

            if (response.ok) {
                // Auto-login after successful registration
                login(data.access_token, data.user_id, data.username);
                window.location.href = "/";
            } else {
                // Handle Pydantic validation errors (list of objects)
                const detail = data.detail;
                if (Array.isArray(detail)) {
                    setError(detail[0]?.msg || "Validation error");
                } else if (typeof detail === 'object' && detail !== null) {
                    setError(JSON.stringify(detail));
                } else {
                    setError(detail || "Failed to create account");
                }
            }
        } catch (err) {
            setError("Network error. Please check the backend is running.");
        } finally {
            setLoading(false);
        }
    };

    const testLBSKey = async () => {
        if (!formData.lbs_api_key) {
            setTestStatus({ type: "error", message: "Key required" });
            return;
        }
        setTestStatus({ type: "loading", message: "Testing..." });
        try {
            const response = await fetch("/api/auth/test-lbs-connection", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ api_key: formData.lbs_api_key }),
            });
            const data = await response.json();
            if (data.status === "success") {
                setTestStatus({ type: "success", message: "Valid Key!" });
            } else {
                setTestStatus({ type: "error", message: data.message });
            }
        } catch (err) {
            setTestStatus({ type: "error", message: "LBS Unreachable" });
        }
    };

    const testKCKey = async () => {
        if (!formData.kc_api_key) {
            setKcTestStatus({ type: "error", message: "Key required" });
            return;
        }
        setKcTestStatus({ type: "loading", message: "Testing..." });
        try {
            const response = await fetch("/api/auth/test-kc-connection", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ api_key: formData.kc_api_key }),
            });
            const data = await response.json();
            if (data.status === "success") {
                setKcTestStatus({ type: "success", message: "Valid Key!" });
            } else {
                setKcTestStatus({ type: "error", message: data.message });
            }
        } catch (err) {
            setKcTestStatus({ type: "error", message: "KC Unreachable" });
        }
    };

    return (
        <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
            <div className="w-full max-w-md">
                {/* Logo/Header */}
                <div className="text-center mb-8">
                    <div className="inline-flex items-center justify-center w-20 h-20 bg-gradient-to-br from-blue-500 to-purple-600 rounded-2xl mb-4 shadow-lg shadow-purple-500/25">
                        <span className="text-4xl">🧠</span>
                    </div>
                    <h1 className="text-3xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
                        Create Account
                    </h1>
                    <p className="text-gray-400 mt-2">Get started with AI TaskManagement OS</p>
                </div>

                {/* Registration Form */}
                <div className="bg-gray-900 border border-gray-800 rounded-2xl p-8 shadow-xl">
                    <form onSubmit={handleSubmit} className="space-y-5">
                        <div>
                            <label htmlFor="username" className="block text-sm font-medium text-gray-300 mb-2">
                                Username *
                            </label>
                            <input
                                type="text"
                                id="username"
                                name="username"
                                value={formData.username}
                                onChange={handleChange}
                                placeholder="your_username"
                                autoComplete="username"
                                className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors"
                            />
                            {!isUsernameValid && formData.username.length > 0 && (
                                <p className="text-red-400 text-xs mt-1">Username must be at least 3 characters</p>
                            )}
                        </div>

                        <div>
                            <label htmlFor="email" className="block text-sm font-medium text-gray-300 mb-2">
                                Email <span className="text-gray-500">(optional)</span>
                            </label>
                            <input
                                type="email"
                                id="email"
                                name="email"
                                value={formData.email}
                                onChange={handleChange}
                                placeholder="you@example.com"
                                autoComplete="email"
                                className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors"
                            />
                        </div>

                        <div>
                            <label htmlFor="password" className="block text-sm font-medium text-gray-300 mb-2">
                                Password *
                            </label>
                            <input
                                type="password"
                                id="password"
                                name="password"
                                value={formData.password}
                                onChange={handleChange}
                                placeholder="Min 8 characters"
                                autoComplete="new-password"
                                className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors"
                            />
                            {!isPasswordValid && formData.password.length > 0 && (
                                <p className="text-red-400 text-xs mt-1">Password must be at least 8 characters</p>
                            )}
                        </div>

                        <div>
                            <label htmlFor="confirmPassword" className="block text-sm font-medium text-gray-300 mb-2">
                                Confirm Password *
                            </label>
                            <input
                                type="password"
                                id="confirmPassword"
                                name="confirmPassword"
                                value={formData.confirmPassword}
                                onChange={handleChange}
                                placeholder="Confirm your password"
                                autoComplete="new-password"
                                className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors"
                            />
                            {!isConfirmValid && formData.confirmPassword.length > 0 && (
                                <p className="text-red-400 text-xs mt-1">Passwords do not match</p>
                            )}
                        </div>

                        <div className="pt-2">
                            <label htmlFor="lbs_api_key" className="block text-sm font-medium text-blue-300 mb-2">
                                LBS API Key *
                            </label>
                            <div className="flex gap-2">
                                <input
                                    type="password"
                                    id="lbs_api_key"
                                    name="lbs_api_key"
                                    value={formData.lbs_api_key}
                                    onChange={handleChange}
                                    placeholder="LBS-XXXXXXXXXXXX"
                                    className="flex-1 px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors"
                                />
                                <button
                                    type="button"
                                    onClick={testLBSKey}
                                    className={`px-4 py-3 rounded-lg font-medium transition-all ${testStatus?.type === 'success'
                                        ? 'bg-green-500/20 text-green-400 border border-green-500/30'
                                        : 'bg-blue-600 hover:bg-blue-700 text-white'
                                        }`}
                                >
                                    {testStatus?.type === 'loading' ? '⏳' : testStatus?.type === 'success' ? '✓' : 'Verify'}
                                </button>
                            </div>
                            {testStatus && (
                                <p className={`mt-1 text-xs ${testStatus.type === 'success' ? 'text-green-400' : 'text-red-400'}`}>
                                    {testStatus.message}
                                </p>
                            )}
                            <p className="text-[10px] text-gray-500 mt-1">
                                Vision Ark requires an LBS API Key for task scheduling features.
                            </p>
                        </div>

                        <div className="pt-2">
                            <label htmlFor="kc_api_key" className="block text-sm font-medium text-blue-300 mb-2">
                                KnowledgeCore API Key *
                            </label>
                            <div className="flex gap-2">
                                <input
                                    type="password"
                                    id="kc_api_key"
                                    name="kc_api_key"
                                    value={formData.kc_api_key}
                                    onChange={handleChange}
                                    placeholder="KC-XXXXXXXXXXXX"
                                    className="flex-1 px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors"
                                />
                                <button
                                    type="button"
                                    onClick={testKCKey}
                                    className={`px-4 py-3 rounded-lg font-medium transition-all ${kcTestStatus?.type === 'success'
                                        ? 'bg-green-500/20 text-green-400 border border-green-500/30'
                                        : 'bg-blue-600 hover:bg-blue-700 text-white'
                                        }`}
                                >
                                    {kcTestStatus?.type === 'loading' ? '⏳' : kcTestStatus?.type === 'success' ? '✓' : 'Verify'}
                                </button>
                            </div>
                            {kcTestStatus && (
                                <p className={`mt-1 text-xs ${kcTestStatus.type === 'success' ? 'text-green-400' : 'text-red-400'}`}>
                                    {kcTestStatus.message}
                                </p>
                            )}
                            <p className="text-[10px] text-gray-500 mt-1">
                                KnowledgeCore provides persistent memory and contextual awareness for your agents.
                            </p>
                        </div>

                        <div>
                            <label htmlFor="gemini_api_key" className="block text-sm font-medium text-blue-300 mb-2">
                                Gemini API Key *
                            </label>
                            <input
                                type="password"
                                id="gemini_api_key"
                                name="gemini_api_key"
                                value={formData.gemini_api_key}
                                onChange={handleChange}
                                placeholder="AIzaSy..."
                                className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-colors"
                            />
                            <p className="text-[10px] text-gray-500 mt-1">
                                Your Gemini API Key is required for the system agents.
                            </p>
                        </div>

                        {error && (
                            <div className="bg-red-500/10 border border-red-500/30 text-red-400 text-sm p-3 rounded-lg">
                                {error}
                            </div>
                        )}

                        <button
                            type="submit"
                            disabled={loading || !isFormValid}
                            className="w-full py-3 px-4 bg-gradient-to-r from-blue-500 to-purple-600 text-white font-semibold rounded-lg hover:from-blue-600 hover:to-purple-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-gray-900 transition-all disabled:opacity-30 disabled:cursor-not-allowed"
                        >
                            {loading ? (
                                <span className="flex items-center justify-center gap-2">
                                    <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                                    </svg>
                                    Creating Account...
                                </span>
                            ) : (
                                "Create Account"
                            )}
                        </button>
                    </form>

                    {/* Divider */}
                    <div className="relative my-6">
                        <div className="absolute inset-0 flex items-center">
                            <div className="w-full border-t border-gray-700"></div>
                        </div>
                        <div className="relative flex justify-center text-sm">
                            <span className="px-2 bg-gray-900 text-gray-500">Already have an account?</span>
                        </div>
                    </div>

                    {/* Sign In Link */}
                    <Link
                        href="/auth/signin"
                        className="block w-full py-3 px-4 text-center border border-gray-700 text-gray-300 font-medium rounded-lg hover:bg-gray-800 hover:border-gray-600 transition-colors"
                    >
                        Sign In
                    </Link>
                </div>
            </div>
        </div>
    );
}
