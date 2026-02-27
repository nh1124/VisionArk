import React, { useState } from "react"
import { login } from "../lib/api"

interface Props {
    onLogin: (username: string) => void
}

export default function LoginScreen({ onLogin }: Props) {
    const [username, setUsername] = useState("")
    const [password, setPassword] = useState("")
    const [error, setError] = useState("")
    const [loading, setLoading] = useState(false)

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        if (!username || !password) return
        setLoading(true)
        setError("")
        try {
            await login(username, password)
            onLogin(username)
        } catch {
            setError("Invalid username or password")
        } finally {
            setLoading(false)
        }
    }

    return (
        <div className="h-screen flex items-center justify-center bg-gray-950">
            <div className="w-full max-w-sm">
                <div className="flex flex-col items-center mb-8">
                    <div className="w-14 h-14 bg-blue-600 rounded-2xl flex items-center justify-center font-bold text-white text-xl mb-3">
                        V
                    </div>
                    <h1 className="text-xl font-bold text-white">Vision Ark</h1>
                    <p className="text-xs text-gray-500 mt-1">AI TaskManagement OS</p>
                </div>

                <form onSubmit={handleSubmit} className="bg-gray-900/40 border border-gray-800 rounded-2xl p-6 space-y-4">
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

                    {error && (
                        <p className="text-xs text-red-400">{error}</p>
                    )}

                    <button
                        type="submit"
                        disabled={loading || !username || !password}
                        className="w-full py-2.5 bg-cyan-500 hover:bg-cyan-400 text-white font-semibold text-sm rounded-xl transition-colors disabled:opacity-50 shadow-lg shadow-cyan-500/20"
                    >
                        {loading ? "Signing in..." : "Sign In"}
                    </button>
                </form>
            </div>
        </div>
    )
}
