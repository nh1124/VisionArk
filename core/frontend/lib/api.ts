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

    // Use relative URL - Next.js rewrites will proxy /api/* to backend
    return fetch(url, {
        ...restOptions,
        headers,
    });
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
