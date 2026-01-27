"use client";

import { useState, useEffect } from "react";
import { apiFetch, apiJson } from "@/lib/api";

type Tab = "account" | "services" | "integrations" | "ai";

interface Service {
    id: number;
    service_name: string;
    base_url: string;
    is_active: boolean;
    health_status?: string;
    last_health_check?: string;
    config?: Record<string, any>;
}

interface Integration {
    issuer: string;
    subject: string;
    linked_at: string;
}

export default function SettingsPage() {
    const [activeTab, setActiveTab] = useState<Tab>("account");
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false); // Used for loading state during saves
    const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

    // Data states
    const [profile, setProfile] = useState({ id: "", username: "", email: "" });
    const [aiConfig, setAiConfig] = useState({ gemini_api_key: "" });
    const [services, setServices] = useState<Service[]>([]);
    const [integrations, setIntegrations] = useState<Integration[]>([]);

    // Form states
    const [passForm, setPassForm] = useState({ current: "", new: "", confirm: "" });
    const [newService, setNewService] = useState({ service_name: "", base_url: "", api_key: "", config: "{}" });

    // Hub UI States
    const [filter, setFilter] = useState<'all' | 'productivity' | 'communication' | 'developer'>('all');
    const [configModal, setConfigModal] = useState<string | null>(null);

    const HUB_CATALOG = [
        {
            id: 'google_calendar',
            name: 'Google Calendar',
            description: 'Sync your schedule and VA tasks across Google ecosystem.',
            icon: '📅',
            color: 'bg-white/10 text-blue-400',
            category: 'productivity',
            authType: 'oauth'
        },
        {
            id: 'outlook',
            name: 'Outlook Calendar',
            description: 'Microsoft 365 integration for professional time management.',
            icon: '📧',
            color: 'bg-blue-600/10 text-blue-500',
            category: 'productivity',
            authType: 'oauth'
        },
        {
            id: 'line',
            name: 'LINE Messaging',
            description: 'AI interaction via LINE bot with automated project isolation.',
            icon: '💬',
            color: 'bg-green-600/10 text-green-500',
            category: 'communication',
            authType: 'manual'
        }
    ];

    useEffect(() => {
        loadSettings();
    }, []);

    const loadSettings = async () => {
        try {
            const data = await apiJson<any>("/api/settings");
            setProfile(data.profile || { id: "", username: "", email: "" });
            setAiConfig({ gemini_api_key: data.ai_config?.gemini_api_key || "" });
            setServices(data.services || []);
            setIntegrations(data.integrations || []);
        } catch (err) {
            console.error("Failed to load settings:", err);
            showMessage("error", "Failed to load settings");
        } finally {
            setLoading(false);
        }
    };

    const showMessage = (type: "success" | "error", text: string) => {
        setMessage({ type, text });
        setTimeout(() => setMessage(null), 5000);
    };

    const handlePasswordChange = async (e: React.FormEvent) => {
        e.preventDefault();
        if (passForm.new !== passForm.confirm) {
            showMessage("error", "Passwords do not match");
            return;
        }
        setSaving(true);
        try {
            await apiJson("/api/settings/account/password", {
                method: "POST",
                body: JSON.stringify({ current_password: passForm.current, new_password: passForm.new })
            });
            showMessage("success", "Password changed successfully");
            setPassForm({ current: "", new: "", confirm: "" });
        } catch (err: any) {
            showMessage("error", err.message || "Failed to change password");
        } finally {
            setSaving(false);
        }
    };

    const copyToClipboard = (text: string) => {
        navigator.clipboard.writeText(text);
        showMessage("success", "Copied to clipboard");
    };

    const saveAiConfig = async () => {
        setSaving(true);
        try {
            await apiJson("/api/settings/ai", {
                method: "PATCH",
                body: JSON.stringify(aiConfig)
            });
            showMessage("success", "AI settings saved");
        } catch (err: any) {
            showMessage("error", err.message || "Failed to save AI settings");
        } finally {
            setSaving(false);
        }
    };

    const registerService = async () => {
        if (!newService.service_name || !newService.base_url) {
            showMessage("error", "Service name and URL are required");
            return;
        }

        let parsedConfig = {};
        try {
            parsedConfig = JSON.parse(newService.config || "{}");
        } catch (e) {
            showMessage("error", "Invalid JSON in configuration field");
            return;
        }

        setSaving(true);
        try {
            await apiJson("/api/settings/services", {
                method: "POST",
                body: JSON.stringify({
                    ...newService,
                    config: parsedConfig
                })
            });
            showMessage("success", `Service ${newService.service_name} registered`);
            setNewService({ service_name: "", base_url: "", api_key: "", config: "{}" });
            loadSettings();
        } catch (err: any) {
            showMessage("error", err.message || "Failed to register service");
        } finally {
            setSaving(false);
        }
    };


    const updateLbsService = async () => {
        if (!newService.api_key) {
            showMessage("error", "LBS API Key is required");
            return;
        }
        setSaving(true);
        try {
            // Use default LBS URL
            const lbsServiceData = {
                service_name: "lbs",
                base_url: "http://host.docker.internal:8001/api/lbs",
                api_key: newService.api_key
            };
            await apiJson("/api/settings/services", {
                method: "POST",
                body: JSON.stringify(lbsServiceData)
            });
            showMessage("success", "LBS configuration updated successfully");
            setNewService({ service_name: "", base_url: "", api_key: "", config: "{}" });
            loadSettings();
        } catch (err: any) {
            showMessage("error", err.message || "Failed to update LBS");
        } finally {
            setSaving(false);
        }
    };

    const updateKcService = async () => {
        if (!newService.api_key) {
            showMessage("error", "KnowledgeCore API Key is required");
            return;
        }
        setSaving(true);
        try {
            // Use default KC URL
            const kcServiceData = {
                service_name: "knowledge_core",
                base_url: "http://host.docker.internal:8200",
                api_key: newService.api_key
            };
            await apiJson("/api/settings/services", {
                method: "POST",
                body: JSON.stringify(kcServiceData)
            });
            showMessage("success", "KnowledgeCore configuration updated successfully");
            setNewService({ service_name: "", base_url: "", api_key: "", config: "{}" });
            loadSettings();
        } catch (err: any) {
            showMessage("error", err.message || "Failed to update KnowledgeCore");
        } finally {
            setSaving(false);
        }
    };

    const testKCConnection = async () => {
        if (!newService.api_key) {
            showMessage("error", "KnowledgeCore API Key is required for testing");
            return;
        }
        setSaving(true);
        try {
            const res = await apiJson<any>("/api/settings/test-connection", {
                method: "POST",
                body: JSON.stringify({
                    base_url: "http://host.docker.internal:8200",
                    api_key: newService.api_key
                })
            });
            if (res.status === "success") {
                showMessage("success", res.message);
            } else {
                showMessage("error", res.message);
            }
        } catch (err: any) {
            showMessage("error", err.message || "Test failed");
        } finally {
            setSaving(false);
        }
    };

    const testConnection = async () => {
        const url = newService.service_name === "lbs" && !newService.base_url
            ? "http://host.docker.internal:8001/api/lbs"
            : newService.base_url;

        if (!url || !newService.api_key) {
            showMessage("error", "URL and API Key are required for testing");
            return;
        }
        setSaving(true);
        try {
            const res = await apiJson<any>("/api/settings/test-connection", {
                method: "POST",
                body: JSON.stringify({ base_url: url, api_key: newService.api_key })
            });
            if (res.status === "success") {
                showMessage("success", res.message);
            } else {
                showMessage("error", res.message);
            }
        } catch (err: any) {
            showMessage("error", err.message || "Test failed");
        } finally {
            setSaving(false);
        }
    };

    const testLbsConnection = async () => {
        if (!newService.api_key) {
            showMessage("error", "LBS API Key is required for testing");
            return;
        }
        setSaving(true);
        try {
            const res = await apiJson<any>("/api/settings/test-connection", {
                method: "POST",
                body: JSON.stringify({
                    base_url: "http://host.docker.internal:8001/api/lbs",
                    api_key: newService.api_key
                })
            });
            if (res.status === "success") {
                showMessage("success", res.message);
            } else {
                showMessage("error", res.message);
            }
        } catch (err: any) {
            showMessage("error", err.message || "Test failed");
        } finally {
            setSaving(false);
        }
    };

    const checkHealth = async (id: number) => {
        try {
            await apiFetch(`/api/settings/services/${id}/health`);
            // Refresh list to show updated status
            loadSettings();
        } catch (err) {
            console.error("Health check failed", err);
        }
    };

    const connectGoogleCalendar = async () => {
        if (!profile.id) {
            showMessage("error", "Profile not loaded. Please refresh the page.");
            return;
        }
        try {
            const res = await apiJson<any>(`/api/google-calendar/auth?user_id=${profile.id}`);
            if (res.auth_url) {
                window.location.href = res.auth_url;
            }
        } catch (err: any) {
            showMessage("error", err.message || "Failed to start Google auth");
        }
    };

    const connectOutlook = async () => {
        if (!profile.id) {
            showMessage("error", "Profile not loaded. Please refresh the page.");
            return;
        }
        try {
            const res = await apiJson<any>(`/api/outlook/auth?user_id=${profile.id}`);
            if (res.auth_url) {
                window.location.href = res.auth_url;
            }
        } catch (err: any) {
            showMessage("error", err.message || "Failed to start Outlook auth");
        }
    };

    const disconnectService = async (serviceName: string) => {
        if (!profile.id) return;
        if (!window.confirm(`Are you sure you want to disconnect ${serviceName.replace('_', ' ')}?`)) return;

        setSaving(true);
        try {
            // Determine endpoint based on service name (convention: /api/[service-slug]/disconnect)
            const slug = serviceName.replace('_', '-');
            await apiJson(`/api/${slug}/disconnect?user_id=${profile.id}`, {
                method: "DELETE"
            });
            showMessage("success", `${serviceName.replace('_', ' ')} disconnected successfully`);
            setConfigModal(null);
            loadSettings();
        } catch (err: any) {
            showMessage("error", err.message || `Failed to disconnect ${serviceName}`);
        } finally {
            setSaving(false);
        }
    };

    if (loading) return <div className="p-8 animate-pulse text-gray-500">Loading settings...</div>;

    return (
        <div className="p-8 max-w-5xl mx-auto">
            <div className="flex items-center justify-between mb-8">
                <div>
                    <h1 className="text-3xl font-bold mb-2">Settings</h1>
                    <p className="text-gray-400 text-sm">Manage your account, microservices, and AI configurations.</p>
                </div>
                {message && (
                    <div className={`px-4 py-2 rounded-lg text-sm font-medium ${message.type === 'success' ? 'bg-green-500/10 text-green-400 border border-green-500/50' : 'bg-red-500/10 text-red-400 border border-red-500/50'}`}>
                        {message.text}
                    </div>
                )}
            </div>

            <div className="flex flex-col md:flex-row gap-8">
                {/* Navigation Sidebar */}
                <div className="w-full md:w-64 space-y-1">
                    <button
                        onClick={() => setActiveTab("account")}
                        className={`w-full text-left px-4 py-3 rounded-lg font-medium transition-colors ${activeTab === 'account' ? 'bg-blue-600 text-white shadow-lg shadow-blue-900/20' : 'text-gray-400 hover:bg-gray-900 hover:text-gray-200'}`}
                    >
                        Account & Security
                    </button>
                    <button
                        onClick={() => setActiveTab("ai")}
                        className={`w-full text-left px-4 py-3 rounded-lg font-medium transition-colors ${activeTab === 'ai' ? 'bg-blue-600 text-white shadow-lg shadow-blue-900/20' : 'text-gray-400 hover:bg-gray-900 hover:text-gray-200'}`}
                    >
                        AI Providers
                    </button>
                    <button
                        onClick={() => setActiveTab("services")}
                        className={`w-full text-left px-4 py-3 rounded-lg font-medium transition-colors ${activeTab === 'services' ? 'bg-blue-600 text-white shadow-lg shadow-blue-900/20' : 'text-gray-400 hover:bg-gray-900 hover:text-gray-200'}`}
                    >
                        Microservices
                    </button>
                    <button
                        onClick={() => setActiveTab("integrations")}
                        className={`w-full text-left px-4 py-3 rounded-lg font-medium transition-colors ${activeTab === 'integrations' ? 'bg-blue-600 text-white shadow-lg shadow-blue-900/20' : 'text-gray-400 hover:bg-gray-900 hover:text-gray-200'}`}
                    >
                        Integrations
                    </button>
                </div>

                {/* Content Area */}
                <div className="flex-1 min-h-[400px]">

                    {/* Account Tab */}
                    {activeTab === "account" && (
                        <div className="space-y-8 animate-in fade-in duration-300">
                            {/* Profile Information */}
                            <div className="bg-gray-900 border border-gray-800 rounded-xl p-8">
                                <h2 className="text-xl font-bold mb-4">Account Profile</h2>
                                <p className="text-gray-400 text-sm mb-6">Your personal account identification and contact details.</p>

                                <div className="space-y-4 max-w-md">
                                    <div>
                                        <label className="block text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">User ID (Webhook usage)</label>
                                        <div className="flex gap-2">
                                            <input
                                                type="text"
                                                readOnly
                                                value={profile.id}
                                                className="w-full bg-gray-950 border border-gray-800 rounded-lg px-4 py-2 text-gray-400 font-mono text-sm outline-none"
                                            />
                                            <button
                                                onClick={() => copyToClipboard(profile.id)}
                                                className="bg-gray-800 hover:bg-gray-700 text-gray-300 px-3 py-2 rounded-lg text-xs font-medium transition-colors"
                                            >
                                                Copy
                                            </button>
                                        </div>
                                    </div>
                                    <div>
                                        <label className="block text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">Username</label>
                                        <input
                                            type="text"
                                            readOnly
                                            value={profile.username}
                                            className="w-full bg-gray-950 border border-gray-800 rounded-lg px-4 py-2 text-gray-400 outline-none"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">Email Address</label>
                                        <input
                                            type="text"
                                            readOnly
                                            value={profile.email || "No email provided"}
                                            className="w-full bg-gray-950 border border-gray-800 rounded-lg px-4 py-2 text-gray-400 outline-none"
                                        />
                                    </div>
                                </div>
                            </div>

                            <div className="bg-gray-900 border border-gray-800 rounded-xl p-8">
                                <h2 className="text-xl font-bold mb-4">Security</h2>
                                <p className="text-gray-400 text-sm mb-6">Update your account password to keep your data secure.</p>

                                <form onSubmit={handlePasswordChange} className="space-y-4 max-w-md">
                                    <div>
                                        <label className="block text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">Current Password</label>
                                        <input
                                            type="password"
                                            required
                                            value={passForm.current}
                                            onChange={(e) => setPassForm(p => ({ ...p, current: e.target.value }))}
                                            className="w-full bg-gray-950 border border-gray-800 rounded-lg px-4 py-2 focus:border-blue-500 outline-none"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">New Password (min 8 chars)</label>
                                        <input
                                            type="password"
                                            required
                                            value={passForm.new}
                                            onChange={(e) => setPassForm(p => ({ ...p, new: e.target.value }))}
                                            className="w-full bg-gray-950 border border-gray-800 rounded-lg px-4 py-2 focus:border-blue-500 outline-none"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">Confirm New Password</label>
                                        <input
                                            type="password"
                                            required
                                            value={passForm.confirm}
                                            onChange={(e) => setPassForm(p => ({ ...p, confirm: e.target.value }))}
                                            className="w-full bg-gray-950 border border-gray-800 rounded-lg px-4 py-2 focus:border-blue-500 outline-none"
                                        />
                                    </div>
                                    <button
                                        type="submit"
                                        disabled={saving}
                                        className="bg-blue-600 hover:bg-blue-500 text-white px-6 py-2 rounded-lg font-medium transition-colors disabled:opacity-50"
                                    >
                                        {saving ? "Saving..." : "Change Password"}
                                    </button>
                                </form>
                            </div>

                            <div className="bg-gray-900 border border-gray-800 rounded-xl p-8">
                                <h2 className="text-xl font-bold mb-4 text-red-500">Danger Zone</h2>
                                <p className="text-gray-400 text-sm mb-4">Permanently delete your account and all associated data. This action cannot be undone.</p>
                                <button className="bg-red-500/10 text-red-500 border border-red-500/50 px-6 py-2 rounded-lg font-medium hover:bg-red-500 hover:text-white transition-all">
                                    Delete Account
                                </button>
                            </div>
                        </div>
                    )}

                    {/* AI Providers Tab */}
                    {activeTab === "ai" && (
                        <div className="animate-in fade-in duration-300">
                            <div className="bg-gray-900 border border-gray-800 rounded-xl p-8">
                                <h2 className="text-xl font-bold mb-4">Gemini Configuration</h2>
                                <p className="text-gray-400 mb-6 text-sm">
                                    Configure your Google Gemini API key here. Model selection is now available directly in the chat interface.
                                </p>

                                <div className="space-y-6">
                                    <div className="bg-gray-800/50 border border-gray-700/50 p-6 rounded-xl">
                                        <div className="flex items-center mb-4">
                                            <div className="w-10 h-10 bg-blue-600/20 rounded-lg flex items-center justify-center mr-3">
                                                <span className="text-xl">♊</span>
                                            </div>
                                            <div>
                                                <h3 className="font-semibold">Google Gemini</h3>
                                                <p className="text-xs text-gray-500">Native multimodal support</p>
                                            </div>
                                        </div>
                                        <div className="space-y-4">
                                            <div>
                                                <label className="block text-sm font-medium text-gray-400 mb-2">
                                                    API Key
                                                </label>
                                                <input
                                                    type="password"
                                                    value={aiConfig.gemini_api_key}
                                                    onChange={(e) => setAiConfig({ ...aiConfig, gemini_api_key: e.target.value })}
                                                    placeholder="Enter your Gemini API key"
                                                    className="w-full px-4 py-2.5 bg-gray-900 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500 transition-colors"
                                                />
                                            </div>
                                            <button
                                                onClick={saveAiConfig}
                                                disabled={saving}
                                                className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors disabled:opacity-50"
                                            >
                                                {saving ? 'Saving...' : 'Update Gemini Key'}
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Services Tab */}
                    {activeTab === "services" && (
                        <div className="animate-in fade-in duration-300">
                            <div className="bg-gray-900 border border-gray-800 rounded-xl p-8">
                                <h2 className="text-xl font-bold mb-4">Service Registry</h2>

                                {/* LBS Quick Setup - Essential Component */}
                                <div className="mb-8 bg-gradient-to-r from-blue-900/20 to-purple-900/20 border border-blue-700/30 p-6 rounded-xl">
                                    <div className="flex items-center gap-3 mb-4">
                                        <div className="w-10 h-10 bg-blue-600/20 rounded-lg flex items-center justify-center">
                                            <span className="text-xl">📅</span>
                                        </div>
                                        <div>
                                            <h3 className="font-bold text-blue-300">LBS - Load Balancing System</h3>
                                            <p className="text-xs text-gray-400">Essential task scheduling microservice</p>
                                        </div>
                                        {services.find(s => s.service_name === "lbs")?.health_status === "healthy" && (
                                            <span className="ml-auto px-2 py-1 bg-green-500/10 text-green-400 text-xs font-bold rounded-full">✓ Connected</span>
                                        )}
                                    </div>

                                    <div className="grid grid-cols-1 gap-4 mb-4">
                                        <div>
                                            <label className="block text-xs font-medium text-gray-500 mb-1">LBS API Key</label>
                                            <input
                                                type="password"
                                                value={newService.service_name === "lbs" ? newService.api_key : ""}
                                                onChange={(e) => setNewService({ ...newService, service_name: "lbs", api_key: e.target.value })}
                                                placeholder="LBS-XXXXXXXXXXXX"
                                                className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white text-sm"
                                            />
                                        </div>
                                    </div>

                                    <div className="flex gap-3 items-end">
                                        <button
                                            onClick={updateLbsService}
                                            disabled={saving || !newService.api_key}
                                            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg font-medium transition-colors disabled:opacity-50 text-sm"
                                        >
                                            {saving ? 'Connecting...' : services.find(s => s.service_name === "lbs") ? 'Update LBS' : 'Connect LBS'}
                                        </button>
                                        <button
                                            onClick={testLbsConnection}
                                            disabled={saving || !newService.api_key}
                                            className="px-4 py-2 bg-purple-600/20 hover:bg-purple-600/30 text-purple-400 border border-purple-500/30 rounded-lg font-medium transition-colors disabled:opacity-50 text-sm"
                                        >
                                            Test Connection
                                        </button>
                                        {services.find(s => s.service_name === "lbs") && (
                                            <button
                                                onClick={() => checkHealth(services.find(s => s.service_name === "lbs")!.id)}
                                                className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg font-medium transition-colors text-sm"
                                            >
                                                Check Health
                                            </button>
                                        )}
                                    </div>

                                    <div className="mt-4 text-xs text-gray-500 bg-gray-950/50 p-3 rounded-lg border border-gray-800">
                                        <strong className="text-gray-400">Note:</strong> LBS uses its own API Key for authentication. User identification is handled automatically via the key.
                                    </div>
                                </div>

                                {/* KnowledgeCore Quick Setup */}
                                <div className="mb-8 bg-gradient-to-r from-blue-900/20 to-green-900/20 border border-green-700/30 p-6 rounded-xl">
                                    <div className="flex items-center gap-3 mb-4">
                                        <div className="w-10 h-10 bg-green-600/20 rounded-lg flex items-center justify-center">
                                            <span className="text-xl">🧠</span>
                                        </div>
                                        <div>
                                            <h3 className="font-bold text-green-300">KnowledgeCore - Persistent Memory</h3>
                                            <p className="text-xs text-gray-400">Long-term memory and context retrieval</p>
                                        </div>
                                        {services.find(s => s.service_name === "knowledge_core")?.health_status === "healthy" && (
                                            <span className="ml-auto px-2 py-1 bg-green-500/10 text-green-400 text-xs font-bold rounded-full">✓ Connected</span>
                                        )}
                                    </div>

                                    <div className="grid grid-cols-1 gap-4 mb-4">
                                        <div>
                                            <label className="block text-xs font-medium text-gray-500 mb-1">KnowledgeCore API Key</label>
                                            <input
                                                type="password"
                                                value={newService.service_name === "knowledge_core" ? newService.api_key : ""}
                                                onChange={(e) => setNewService({ ...newService, service_name: "knowledge_core", api_key: e.target.value })}
                                                placeholder="KC-XXXXXXXXXXXX"
                                                className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white text-sm"
                                            />
                                        </div>
                                    </div>

                                    <div className="flex gap-3 items-end">
                                        <button
                                            onClick={updateKcService}
                                            disabled={saving || !newService.api_key}
                                            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg font-medium transition-colors disabled:opacity-50 text-sm"
                                        >
                                            {saving ? 'Connecting...' : services.find(s => s.service_name === "knowledge_core") ? 'Update KC' : 'Connect KC'}
                                        </button>
                                        <button
                                            onClick={testKCConnection}
                                            disabled={saving || !newService.api_key}
                                            className="px-4 py-2 bg-green-600/20 hover:bg-green-600/30 text-green-400 border border-green-500/30 rounded-lg font-medium transition-colors disabled:opacity-50 text-sm"
                                        >
                                            Test Connection
                                        </button>
                                        {services.find(s => s.service_name === "knowledge_core") && (
                                            <button
                                                onClick={() => checkHealth(services.find(s => s.service_name === "knowledge_core")!.id)}
                                                className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg font-medium transition-colors text-sm"
                                            >
                                                Check Health
                                            </button>
                                        )}
                                    </div>

                                    <div className="mt-4 text-xs text-gray-500 bg-gray-950/50 p-3 rounded-lg border border-gray-800">
                                        <strong className="text-gray-400">Note:</strong> KnowledgeCore enhances your agents with long-term memory and relevant context for every interaction.
                                    </div>
                                </div>

                            </div>
                        </div>
                    )}

                    {/* Integrations Tab */}
                    {activeTab === "integrations" && (
                        <div className="space-y-6 animate-in fade-in duration-300">
                            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                                <div>
                                    <h2 className="text-2xl font-bold">Integration Hub</h2>
                                    <p className="text-gray-400 text-sm">Connect VisionArk with your favorite tools and platforms.</p>
                                </div>
                                <div className="flex bg-gray-900 p-1 rounded-lg border border-gray-800">
                                    {(['all', 'productivity', 'communication', 'developer'] as const).map(cat => (
                                        <button
                                            key={cat}
                                            onClick={() => setFilter(cat)}
                                            className={`px-3 py-1.5 rounded-md text-xs font-bold uppercase tracking-wider transition-all ${filter === cat ? 'bg-blue-600 text-white shadow-lg shadow-blue-900/20' : 'text-gray-500 hover:text-gray-300'}`}
                                        >
                                            {cat}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
                                {HUB_CATALOG
                                    .filter(item => filter === 'all' || item.category === filter)
                                    .map(item => {
                                        const service = services.find(s => s.service_name === item.id);
                                        const identity = integrations.find(i => i.issuer === item.id);
                                        const isConnected = !!service?.is_active;

                                        return (
                                            <div
                                                key={item.id}
                                                className={`group bg-gray-900 border ${isConnected ? 'border-blue-500/30 bg-blue-500/[0.02]' : 'border-gray-800'} rounded-2xl p-6 transition-all hover:border-blue-500/50 hover:shadow-2xl hover:shadow-blue-900/10 relative overflow-hidden`}
                                            >
                                                {/* Card Background Glow */}
                                                {isConnected && <div className="absolute -top-12 -right-12 w-24 h-24 bg-blue-600/10 blur-3xl rounded-full" />}

                                                <div className="flex items-start justify-between mb-6">
                                                    <div className={`w-14 h-14 rounded-2xl flex items-center justify-center text-3xl shadow-inner ${item.color}`}>
                                                        {item.icon}
                                                    </div>
                                                    <div className={`px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-widest ${isConnected ? 'bg-green-500/10 text-green-400 border border-green-500/20' : 'bg-gray-800 text-gray-500 border border-gray-700'}`}>
                                                        {isConnected ? 'Connected' : 'Disconnected'}
                                                    </div>
                                                </div>

                                                <div className="mb-6">
                                                    <h3 className="text-lg font-bold mb-1">{item.name}</h3>
                                                    <p className="text-gray-400 text-xs leading-relaxed min-h-[32px]">{item.description}</p>
                                                </div>

                                                {isConnected && (
                                                    <div className="mb-6 p-3 bg-gray-950/50 border border-gray-800 rounded-xl flex items-center gap-3">
                                                        <div className="w-8 h-8 bg-blue-600/20 rounded-full flex items-center justify-center text-xs font-bold text-blue-400">
                                                            {identity?.subject?.[0].toUpperCase() || '?'}
                                                        </div>
                                                        <div className="truncate">
                                                            <p className="text-[10px] text-gray-500 font-bold uppercase">Linked Account</p>
                                                            <p className="text-xs text-gray-300 truncate">{identity?.subject || 'Authenticated Session'}</p>
                                                        </div>
                                                    </div>
                                                )}

                                                <div className="flex gap-2">
                                                    {!isConnected ? (
                                                        <button
                                                            onClick={item.authType === 'oauth' ? (item.id === 'google_calendar' ? connectGoogleCalendar : connectOutlook) : () => setConfigModal(item.id)}
                                                            className="flex-1 bg-blue-600 hover:bg-blue-500 text-white py-2.5 rounded-xl font-bold text-sm transition-all shadow-lg shadow-blue-900/20 active:scale-95"
                                                        >
                                                            Connect {item.name}
                                                        </button>
                                                    ) : (
                                                        <>
                                                            <button
                                                                onClick={() => {
                                                                    setNewService({
                                                                        service_name: item.id,
                                                                        base_url: service?.base_url || "",
                                                                        api_key: "", // Hidden for security
                                                                        config: JSON.stringify(service?.config || {}, null, 2)
                                                                    });
                                                                    setConfigModal(item.id);
                                                                }}
                                                                className="flex-1 bg-gray-800 hover:bg-gray-700 text-gray-200 py-2.5 rounded-xl font-bold text-sm transition-all border border-gray-700"
                                                            >
                                                                Manage
                                                            </button>
                                                            <button
                                                                onClick={() => checkHealth(service!.id)}
                                                                className="w-12 bg-gray-800 hover:bg-gray-700 text-gray-400 py-2.5 rounded-xl flex items-center justify-center border border-gray-700 transition-all"
                                                                title="Refresh Status"
                                                            >
                                                                ↻
                                                            </button>
                                                        </>
                                                    )}
                                                </div>
                                            </div>
                                        );
                                    })}

                                {/* Custom Hook Card */}
                                <div
                                    onClick={() => setConfigModal('custom')}
                                    className="group bg-gray-900 border border-gray-800 border-dashed rounded-2xl p-6 transition-all hover:border-blue-500/50 hover:bg-blue-500/[0.01] cursor-pointer flex flex-col items-center justify-center text-center gap-4"
                                >
                                    <div className="w-14 h-14 bg-gray-800 group-hover:bg-blue-600/20 rounded-2xl flex items-center justify-center text-2xl text-gray-600 group-hover:text-blue-400 transition-all">
                                        +
                                    </div>
                                    <div>
                                        <h3 className="font-bold mb-1">Custom Webhook</h3>
                                        <p className="text-gray-500 text-xs">Connect any proprietary system</p>
                                    </div>
                                </div>
                            </div>

                            {/* Config Modal - Shared for all manual integrations */}
                            {configModal && (
                                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in">
                                    <div className="bg-gray-900 border border-gray-800 w-full max-w-lg rounded-3xl p-8 shadow-2xl">
                                        <div className="flex justify-between items-center mb-6">
                                            <h3 className="text-xl font-bold capitalize">Configure {configModal.replace('_', ' ')}</h3>
                                            <button onClick={() => setConfigModal(null)} className="text-gray-500 hover:text-white">✕</button>
                                        </div>

                                        <div className="space-y-4">
                                            <div>
                                                <label className="block text-xs font-bold text-gray-500 uppercase mb-2">Endpoint URL</label>
                                                <input
                                                    type="text"
                                                    placeholder="https://api.example.com"
                                                    value={newService.base_url}
                                                    onChange={e => setNewService({ ...newService, base_url: e.target.value })}
                                                    className="w-full bg-gray-950 border border-gray-800 rounded-xl px-4 py-3 text-sm focus:border-blue-500 outline-none"
                                                />
                                            </div>
                                            <div>
                                                <label className="block text-xs font-bold text-gray-500 uppercase mb-2">API Key / Secret</label>
                                                <input
                                                    type="password"
                                                    placeholder="Paste your key here"
                                                    value={newService.api_key}
                                                    onChange={e => setNewService({ ...newService, api_key: e.target.value })}
                                                    className="w-full bg-gray-950 border border-gray-800 rounded-xl px-4 py-3 text-sm focus:border-blue-500 outline-none"
                                                />
                                            </div>
                                            <div>
                                                <label className="block text-xs font-bold text-gray-500 uppercase mb-2">Config JSON</label>
                                                <textarea
                                                    placeholder='{ "channel": "main" }'
                                                    value={newService.config}
                                                    onChange={e => setNewService({ ...newService, config: e.target.value })}
                                                    className="w-full bg-gray-950 border border-gray-800 rounded-xl px-4 py-3 text-sm h-32 font-mono focus:border-blue-500 outline-none"
                                                />
                                            </div>

                                            {/* VisionArk Automation Extensions */}
                                            <div className="pt-4 border-t border-gray-800">
                                                <h4 className="text-xs font-bold text-blue-400 uppercase mb-4">VisionArk Automation</h4>
                                                <div className="space-y-3">
                                                    <label className="flex items-center gap-3 cursor-pointer group">
                                                        <input
                                                            type="checkbox"
                                                            checked={(() => {
                                                                try { return JSON.parse(newService.config || "{}").va_auto_meeting_link; }
                                                                catch (e) { return false; }
                                                            })()}
                                                            onChange={e => {
                                                                try {
                                                                    const cfg = JSON.parse(newService.config || "{}");
                                                                    cfg.va_auto_meeting_link = e.target.checked;
                                                                    setNewService({ ...newService, config: JSON.stringify(cfg, null, 2) });
                                                                } catch (err) { console.error("Invalid JSON in config", err); }
                                                            }}
                                                            className="w-4 h-4 rounded border-gray-700 bg-gray-950 text-blue-600 focus:ring-blue-500"
                                                        />
                                                        <div className="text-sm">
                                                            <p className="text-gray-200 font-medium">Auto-generate meeting links</p>
                                                            <p className="text-gray-500 text-[11px]">Generate Meet/Teams link for new tasks</p>
                                                        </div>
                                                    </label>
                                                    <label className="flex items-center gap-3 cursor-pointer group">
                                                        <input
                                                            type="checkbox"
                                                            checked={(() => {
                                                                try { return JSON.parse(newService.config || "{}").va_realtime_sync; }
                                                                catch (e) { return false; }
                                                            })()}
                                                            onChange={e => {
                                                                try {
                                                                    const cfg = JSON.parse(newService.config || "{}");
                                                                    cfg.va_realtime_sync = e.target.checked;
                                                                    setNewService({ ...newService, config: JSON.stringify(cfg, null, 2) });
                                                                } catch (err) { console.error("Invalid JSON in config", err); }
                                                            }}
                                                            className="w-4 h-4 rounded border-gray-700 bg-gray-950 text-blue-600 focus:ring-blue-500"
                                                        />
                                                        <div className="text-sm">
                                                            <p className="text-gray-200 font-medium">Enable Real-time Sync</p>
                                                            <p className="text-gray-500 text-[11px]">Listen for changes via Webhooks</p>
                                                        </div>
                                                    </label>
                                                </div>
                                            </div>
                                            <div className="pt-4 flex gap-3">
                                                <button
                                                    onClick={() => {
                                                        const id = configModal === 'custom' ? newService.service_name : configModal;
                                                        if (!id) { showMessage('error', 'Plugin name required'); return; }
                                                        registerService();
                                                        setConfigModal(null);
                                                    }}
                                                    className="flex-1 bg-blue-600 hover:bg-blue-500 text-white py-3 rounded-xl font-bold transition-all"
                                                >
                                                    Save Configuration
                                                </button>
                                                {configModal !== 'custom' && services.some(s => s.service_name === configModal) && (
                                                    <button
                                                        onClick={() => disconnectService(configModal)}
                                                        className="px-6 py-3 bg-red-500/10 text-red-500 border border-red-500/50 rounded-xl font-bold hover:bg-red-500 hover:text-white transition-all"
                                                    >
                                                        Disconnect
                                                    </button>
                                                )}
                                                <button onClick={() => setConfigModal(null)} className="px-6 py-3 text-gray-400 hover:text-white font-bold">Cancel</button>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
