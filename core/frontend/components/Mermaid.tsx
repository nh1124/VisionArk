"use client";

import React, { useEffect, useRef, useState } from "react";

interface MermaidProps {
    chart: string;
}

const Mermaid: React.FC<MermaidProps> = ({ chart }) => {
    const ref = useRef<HTMLDivElement>(null);
    const [libLoaded, setLibLoaded] = useState(false);

    useEffect(() => {
        const loadAndRender = async () => {
            if (!ref.current || !chart) return;

            try {
                let mermaid: any;

                // 1. Check if already in window (from script tag)
                if (typeof window !== "undefined" && (window as any).mermaid) {
                    mermaid = (window as any).mermaid;
                } else {
                    try {
                        // 2. Try to load from CDN first to be safe in Docker envs where bundling fails
                        await new Promise((resolve, reject) => {
                            const script = document.createElement("script");
                            script.src = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js";
                            script.async = true;
                            script.onload = resolve;
                            script.onerror = (e) => {
                                console.warn("CDN load failed, will try local import as last resort");
                                resolve(null); // Continue to local import try
                            };
                            document.head.appendChild(script);
                        });

                        if ((window as any).mermaid) {
                            mermaid = (window as any).mermaid;
                        }
                    } catch (e) {
                        console.error("CDN attempt failed:", e);
                    }
                }

                // 3. Last resort: Try to find it in window if CDN onload was skipped
                if (!mermaid && typeof window !== "undefined") {
                    mermaid = (window as any).mermaid;
                }

                if (!mermaid) {
                    throw new Error("Mermaid library could not be loaded via CDN.");
                }

                if (mermaid) {
                    mermaid.initialize({
                        startOnLoad: false,
                        theme: "dark",
                        securityLevel: "loose",
                        fontFamily: "Inter, sans-serif",
                    });

                    const id = `mermaid-${Math.floor(Math.random() * 1000000)}`;
                    ref.current.removeAttribute("data-processed");
                    ref.current.innerHTML = "";

                    // Async render for v10+
                    const { svg } = await mermaid.render(id, chart);
                    if (ref.current) {
                        ref.current.innerHTML = svg;
                        setLibLoaded(true);
                    }
                }
            } catch (err: any) {
                console.error("Mermaid error:", err);
                if (ref.current) {
                    ref.current.innerHTML = `
                        <div class="p-4 rounded-xl bg-red-950/20 border border-red-900/50 text-red-400 text-[10px] font-mono">
                            <p class="font-bold mb-1">Mermaid Render Error</p>
                            <p>${err.message}</p>
                            <pre class="mt-2 opacity-50 whitespace-pre-wrap">${chart}</pre>
                        </div>
                    `;
                }
            }
        };

        loadAndRender();
    }, [chart]);

    return (
        <div className="mermaid-container flex justify-center my-6 bg-gray-900/10 p-4 rounded-xl border border-gray-800/30 shadow-inner overflow-x-auto min-h-[60px]">
            <div ref={ref} className="mermaid transition-all duration-300 min-w-[200px] flex justify-center" />
        </div>
    );
};

export default Mermaid;
