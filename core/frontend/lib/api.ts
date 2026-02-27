/**
 * API fetch utility with automatic JWT token injection
 * 
 * Browser requests use relative URLs (/api/...) which Next.js rewrites
 * proxy to the backend server (configured in next.config.ts)
 */

interface FetchOptions extends RequestInit {
    skipAuth?: boolean;
}

export async function apiFetch(
    url: string,
    options: FetchOptions = {}
): Promise<Response> {
    const { skipAuth, headers: customHeaders, ...restOptions } = options;

    const headers: Record<string, string> = {
        ...(customHeaders as Record<string, string>),
    };

    // Add Bearer token from localStorage if available and not skipping auth
    if (!skipAuth && typeof window !== "undefined") {
        const accessToken = localStorage.getItem("atmos_access_token");
        if (accessToken) {
            headers["Authorization"] = `Bearer ${accessToken}`;
        }
    }

    // Inject browser timezone for LBS date-boundary accuracy
    if (typeof Intl !== "undefined") {
        headers["X-Timezone"] = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
    }

    // Use relative URL - Next.js rewrites will proxy /api/* to backend
    const response = await fetch(url, {
        ...restOptions,
        headers,
    });

    // Intercept 401 Unauthorized globally
    if (response.status === 401 && typeof window !== "undefined") {
        console.warn("Unauthorized request detected (401), triggering logout signal");
        window.dispatchEvent(new CustomEvent("atmos-auth-error"));
    }

    return response;
}

/**
 * Helper for JSON API calls
 */
export async function apiJson<T>(
    url: string,
    options: FetchOptions = {}
): Promise<T> {
    const response = await apiFetch(url, {
        ...options,
        headers: {
            "Content-Type": "application/json",
            ...options.headers,
        },
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: "Request failed" }));
        throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
}

/**
 * Short-lived File Token Cache
 * Tokens are valid for 5 minutes, we cache for slightly less to be safe
 */
let cachedFileToken: { token: string; expiresAt: number } | null = null;

export async function getFileToken(): Promise<string> {
    const now = Date.now();

    // Check if we have a valid cached token (with 30s buffer)
    if (cachedFileToken && cachedFileToken.expiresAt > now + 30000) {
        return cachedFileToken.token;
    }

    try {
        const data = await apiJson<{ file_token: string; expires_in: number }>("/api/auth/file-token");
        cachedFileToken = {
            token: data.file_token,
            expiresAt: now + (data.expires_in * 1000)
        };
        return data.file_token;
    } catch (error) {
        console.error("Failed to fetch file token:", error);
        throw error;
    }
}
