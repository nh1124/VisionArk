"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

// Redirect to unified Tasks page
export default function ExecutionPageRedirect() {
    const router = useRouter();

    useEffect(() => {
        router.replace("/tasks");
    }, [router]);

    return (
        <div className="min-h-screen bg-gray-950 text-white flex items-center justify-center">
            <div className="text-gray-500 animate-pulse">Redirecting to Tasks...</div>
        </div>
    );
}
