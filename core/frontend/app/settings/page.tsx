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
    const [aiConfig, setAiConfig] = useState({ gemini_api_key: "" });
    const [services, setServices] = useState<Service[]>([]);
    const [integrations, setIntegrations] = useState<Integration[]>([]);

    // Form states
    const [passForm, setPassForm] = useState({ current: "", new: "", confirm: "" });
    const [newService, setNewService] = useState({ service_name: "", base_url: "", api_key: "" });

    useEffect(() => {
        loadSettings();
    }, []);

    const loadSettings = async () => {
        try {
            const data = await apiJson<any>("/api/settings");
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
        setSaving(true);
        try {
            await apiJson("/api/settings/services", {
                method: "POST",
                body: JSON.stringify(newService)
            });
            showMessage("success", `Service ${newService.service_name} registered`);
            setNewService({ service_name: "", base_url: "", api_key: "" });
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
                base_url: "http://host.docker.internal:8100/api/lbs",
                api_key: newService.api_key
            };
            await apiJson("/api/settings/services", {
                method: "POST",
                body: JSON.stringify(lbsServiceData)
            });
            showMessage("success", "LBS configuration updated successfully");
            setNewService({ service_name: "", base_url: "", api_key: "" });
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
            setNewService({ service_name: "", base_url: "", api_key: "" });
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
            ? "http://host.docker.internal:8100/api/lbs"
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
                    base_url: "http://host.docker.internal:8100/api/lbs",
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
                        <div className="animate-in fade-in duration-300">
                            <div className="bg-gray-900 border border-gray-800 rounded-xl p-8">
                                <h2 className="text-xl font-bold mb-4">Linked Accounts</h2>
                                <p className="text-gray-400 text-sm mb-6">Connect your workspace with external identity providers.</p>

                                <div className="space-y-4">
                                    {integrations.length === 0 ? (
                                        <div className="bg-gray-950 p-6 rounded-lg border border-gray-800 text-center">
                                            <p className="text-gray-500 mb-4">You haven't linked any external accounts yet.</p>
                                            <button className="text-blue-400 hover:text-blue-300 font-medium">+ Link External ID</button>
                                        </div>
                                    ) : (
                                        integrations.map((i, idx) => (
                                            <div key={idx} className="bg-gray-950 border border-gray-800 rounded-lg p-6 flex items-center justify-between">
                                                <div className="flex items-center space-x-4">
                                                    <div className="w-12 h-12 bg-gray-800 rounded-full flex items-center justify-center font-bold text-gray-400">
                                                        {i.issuer[0].toUpperCase()}
                                                    </div>
                                                    <div>
                                                        <h3 className="font-bold">{i.issuer}</h3>
                                                        <p className="text-xs text-gray-500">ID: {i.subject}</p>
                                                    </div>
                                                </div>
                                                <div className="text-right">
                                                    <p className="text-xs text-gray-400">Linked on</p>
                                                    <p className="text-sm font-medium">{new Date(i.linked_at).toLocaleDateString()}</p>
                                                </div>
                                            </div>
                                        ))
                                    )}
                                </div>
                            </div>
                        </div>
                    )}

                </div>
            </div>
        </div>
    );
}
