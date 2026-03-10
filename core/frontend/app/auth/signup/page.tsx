"use client";

import { useState } from "react";
import { useAuth } from "@/lib/AuthContext";
import Link from "next/link";
import Image from "next/image";

export default function SignUpPage() {
    const { login } = useAuth();
    const [formData, setFormData] = useState({
        username: "",
        email: "",
        password: "",
        confirmPassword: "",
        gemini_api_key: "",
        openai_api_key: "",
        anthropic_api_key: "",
    });

    const isUsernameValid = formData.username.trim().length >= 3;
    const isPasswordValid = formData.password.length >= 8;
    const isConfirmValid = formData.password === formData.confirmPassword && formData.password !== "";
    const hasAtLeastOneLLMKey = formData.gemini_api_key !== "" || formData.openai_api_key !== "" || formData.anthropic_api_key !== "";
    const isFormValid = isUsernameValid && isPasswordValid && isConfirmValid && hasAtLeastOneLLMKey;
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
                    gemini_api_key: formData.gemini_api_key || undefined,
                    openai_api_key: formData.openai_api_key || undefined,
                    anthropic_api_key: formData.anthropic_api_key || undefined,
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

    return (
        <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
            <div className="w-full max-w-md">
                {/* Logo/Header */}
                <div className="text-center mb-8">
                    <div className="inline-flex items-center justify-center w-20 h-20 bg-blue-600 rounded-2xl mb-4 shadow-lg shadow-blue-500/30 overflow-hidden">
                        <Image
                            src="/icon-192x192.png"
                            alt="VisionArk Logo"
                            width={80}
                            height={80}
                            className="w-full h-full object-cover"
                            priority
                        />
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

                        <div>
                            <label className="block text-sm font-medium text-blue-300 mb-2">
                                LLM API Keys <span className="text-gray-500">(at least one required)</span>
                            </label>
                            <div className="space-y-3">
                                <div>
                                    <label htmlFor="gemini_api_key" className="block text-xs text-gray-400 mb-1">Gemini</label>
                                    <input
                                        type="password"
                                        id="gemini_api_key"
                                        name="gemini_api_key"
                                        value={formData.gemini_api_key}
                                        onChange={handleChange}
                                        placeholder="AIzaSy..."
                                        className="w-full px-4 py-2.5 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 transition-colors"
                                    />
                                </div>
                                <div>
                                    <label htmlFor="openai_api_key" className="block text-xs text-gray-400 mb-1">OpenAI</label>
                                    <input
                                        type="password"
                                        id="openai_api_key"
                                        name="openai_api_key"
                                        value={formData.openai_api_key}
                                        onChange={handleChange}
                                        placeholder="sk-..."
                                        className="w-full px-4 py-2.5 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500 transition-colors"
                                    />
                                </div>
                                <div>
                                    <label htmlFor="anthropic_api_key" className="block text-xs text-gray-400 mb-1">Anthropic</label>
                                    <input
                                        type="password"
                                        id="anthropic_api_key"
                                        name="anthropic_api_key"
                                        value={formData.anthropic_api_key}
                                        onChange={handleChange}
                                        placeholder="sk-ant-..."
                                        className="w-full px-4 py-2.5 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-orange-500 transition-colors"
                                    />
                                </div>
                            </div>
                            {!hasAtLeastOneLLMKey && (
                                <p className="text-yellow-400 text-xs mt-2">⚠ Provide at least one LLM API key</p>
                            )}
                            <p className="text-[10px] text-gray-500 mt-1">
                                Configure at least one LLM provider. You can add more in settings later.
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
