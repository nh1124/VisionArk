"use client";

import React, { createContext, useContext, useState, useEffect, ReactNode } from "react";

interface AuthContextType {
    isAuthenticated: boolean;
    accessToken: string | null;
    userId: string | null;
    username: string | null;
    login: (accessToken: string, userId: string, username: string) => void;
    logout: () => void;
    isLoading: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
    const [isAuthenticated, setIsAuthenticated] = useState(false);
    const [accessToken, setAccessToken] = useState<string | null>(null);
    const [userId, setUserId] = useState<string | null>(null);
    const [username, setUsername] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(true);

    // Check for stored auth on mount
    useEffect(() => {
        const storedToken = localStorage.getItem("atmos_access_token");
        const storedUserId = localStorage.getItem("atmos_user_id");
        const storedUsername = localStorage.getItem("atmos_username");

        if (storedToken) {
            setAccessToken(storedToken);
            setUserId(storedUserId);
            setUsername(storedUsername);
            setIsAuthenticated(true);
        }
        setIsLoading(false);
    }, []);

    const login = (newToken: string, newUserId: string, newUsername: string) => {
        localStorage.setItem("atmos_access_token", newToken);
        localStorage.setItem("atmos_user_id", newUserId);
        localStorage.setItem("atmos_username", newUsername);
        setAccessToken(newToken);
        setUserId(newUserId);
        setUsername(newUsername);
        setIsAuthenticated(true);
    };

    const logout = () => {
        // Call logout endpoint (fire and forget)
        const token = localStorage.getItem("atmos_access_token");
        if (token) {
            fetch("/api/auth/logout", {
                method: "POST",
                headers: {
                    "Authorization": `Bearer ${token}`
                }
            }).catch(() => { }); // Ignore errors
        }

        localStorage.removeItem("atmos_access_token");
        localStorage.removeItem("atmos_user_id");
        localStorage.removeItem("atmos_username");
        setAccessToken(null);
        setUserId(null);
        setUsername(null);
        setIsAuthenticated(false);
    };

    return (
        <AuthContext.Provider
            value={{
                isAuthenticated,
                accessToken,
                userId,
                username,
                login,
                logout,
                isLoading,
            }}
        >
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const context = useContext(AuthContext);
    if (context === undefined) {
        throw new Error("useAuth must be used within an AuthProvider");
    }
    return context;
}
