"use client";

import { useEffect } from "react";

export default function Error({
    error,
    reset,
}: {
    error: Error & { digest?: string };
    reset: () => void;
}) {
    useEffect(() => {
        // Log the error to an error reporting service
        console.error("Application Error:", error);
    }, [error]);

    return (
        <div className="flex h-screen w-full flex-col items-center justify-center bg-gray-950 text-gray-100">
            <div className="w-full max-w-md px-8 text-center">
                <div className="mb-6 inline-flex h-20 w-20 items-center justify-center rounded-2xl bg-red-500/10 shadow-xl shadow-red-900/10 border border-red-500/20">
                    <span className="text-4xl text-red-500">⚠️</span>
                </div>
                <h2 className="mb-3 text-2xl font-bold text-red-400">Something went wrong!</h2>
                <p className="mb-2 text-gray-400 font-mono text-xs bg-gray-900 p-3 rounded-lg border border-gray-800 break-all">
                    {error.message || "Unknown error occurred"}
                </p>
                <p className="mb-8 text-gray-500 text-sm">
                    Please try again or contact support if the problem persists.
                </p>
                <button
                    onClick={
                        // Attempt to recover by trying to re-render the segment
                        () => reset()
                    }
                    className="inline-flex w-full items-center justify-center rounded-xl bg-gray-800 px-6 py-3 font-semibold text-white transition-all hover:bg-gray-700 hover:text-white active:scale-95 border border-gray-700"
                >
                    Try again
                </button>
            </div>
        </div>
    );
}
