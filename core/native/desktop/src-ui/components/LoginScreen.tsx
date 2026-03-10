import React, { useEffect, useState } from "react"
import { ChevronDown, ChevronUp } from "lucide-react"
import { login, getApiBase } from "../lib/api"
import appIcon from "../../icons/icon.png"

interface Props {
    onLogin: (username: string) => void
}

export default function LoginScreen({ onLogin }: Props) {
    const [username, setUsername] = useState("")
    const [password, setPassword] = useState("")
    const [error, setError] = useState("")
    const [loading, setLoading] = useState(false)
    const [showAdvanced, setShowAdvanced] = useState(false)
    const [serverUrl, setServerUrl] = useState("")

    // Populate field with the currently active URL on mount
    useEffect(() => {
        setServerUrl(getApiBase())
    }, [])

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        if (!username || !password) return
        setLoading(true)
        setError("")
        try {
            await login(username, password, serverUrl)
            onLogin(username)
        } catch (e) {
            const message = e instanceof Error ? e.message : "Login failed"
            setError(message)
        } finally {
            setLoading(false)
        }
    }

    return (
        <div className="h-screen flex items-center justify-center bg-gray-950 p-6">
            <div className="w-full max-w-sm">
                <div className="flex flex-col items-center mb-8">
                    <div className="w-16 h-16 rounded-2xl overflow-hidden shadow-lg shadow-blue-500/30 mb-3 border border-blue-500/20">
                        <img
                            src={appIcon}
                            alt="VisionArk logo"
                            className="w-full h-full object-cover"
                        />
                    </div>
                    <h1 className="text-2xl font-bold text-white tracking-tight">VisionArk</h1>
                    <p className="text-sm text-gray-400 mt-1">Sign in to continue</p>
                </div>

                <form onSubmit={handleSubmit} className="bg-gray-900/50 border border-gray-800 rounded-2xl p-6 space-y-4 shadow-xl">
                    <div>
                        <label className="block text-xs font-medium text-gray-400 mb-1.5">Username</label>
                        <input
                            type="text"
                            value={username}
                            onChange={(e) => setUsername(e.target.value)}
                            className="w-full px-3 py-2.5 bg-gray-800 border border-gray-700 rounded-xl text-sm text-white outline-none focus:border-cyan-500 transition-colors"
                            placeholder="Enter username"
                        />
                    </div>

                    <div>
                        <label className="block text-xs font-medium text-gray-400 mb-1.5">Password</label>
                        <input
                            type="password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            className="w-full px-3 py-2.5 bg-gray-800 border border-gray-700 rounded-xl text-sm text-white outline-none focus:border-cyan-500 transition-colors"
                            placeholder="Enter password"
                        />
                    </div>

                    {/* Advanced: server URL */}
                    <div>
                        <button
                            type="button"
                            onClick={() => setShowAdvanced((v) => !v)}
                            className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-300 transition-colors"
                        >
                            {showAdvanced ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                            Advanced
                        </button>
                        {showAdvanced && (
                            <div className="mt-2 space-y-1.5">
                                <label className="block text-xs font-medium text-gray-500">
                                    Server URL
                                </label>
                                <input
                                    type="url"
                                    value={serverUrl}
                                    onChange={(e) => setServerUrl(e.target.value)}
                                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-xl text-sm text-white outline-none focus:border-cyan-500 transition-colors font-mono"
                                    placeholder="http://localhost:8000"
                                />
                                <p className="text-[11px] text-gray-600">
                                    Current: {getApiBase()}
                                </p>
                            </div>
                        )}
                    </div>

                    {error && <p className="text-xs text-red-400">{error}</p>}

                    <button
                        type="submit"
                        disabled={loading || !username || !password}
                        className="w-full py-2.5 bg-cyan-500 hover:bg-cyan-400 text-white font-semibold text-sm rounded-xl transition-colors disabled:opacity-50 shadow-lg shadow-cyan-500/20"
                    >
                        {loading ? "Signing in..." : "Sign In"}
                    </button>
                </form>

                <p className="text-[11px] text-gray-500 text-center mt-4">
                    Create account on web first, then sign in here.
                </p>
            </div>
        </div>
    )
}
