import { NextRequest, NextResponse } from 'next/server';

// Route segment config for large file uploads
export const maxDuration = 300; // 5 minutes timeout
export const dynamic = 'force-dynamic';

// Increase fetch timeout for large file uploads
const FETCH_TIMEOUT = 5 * 60 * 1000; // 5 minutes

export async function POST(
    request: NextRequest,
    { params }: { params: Promise<{ spokeName: string }> }
) {
    const { spokeName } = await params;
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://backend:8000';

    try {
        // Clone the request to read the body
        const contentType = request.headers.get('content-type') || '';

        let body: any;
        let forwardHeaders: HeadersInit = {};

        // Handle different content types
        if (contentType.includes('application/json')) {
            body = await request.text(); // Get raw text to forward as-is
            forwardHeaders['Content-Type'] = 'application/json';
        } else if (contentType.includes('multipart/form-data')) {
            // For multipart, we need to forward the raw body
            body = await request.arrayBuffer();
            forwardHeaders['Content-Type'] = contentType;
        } else {
            // Default: try to get text
            body = await request.text();
            forwardHeaders['Content-Type'] = contentType || 'application/json';
        }

        // Forward authorization headers
        const authHeader = request.headers.get('authorization');
        const cookieHeader = request.headers.get('cookie');
        const modelHeader = request.headers.get('x-preferred-model');
        if (authHeader) forwardHeaders['Authorization'] = authHeader;
        if (cookieHeader) forwardHeaders['Cookie'] = cookieHeader;
        if (modelHeader) forwardHeaders['X-Preferred-Model'] = modelHeader;

        // Forward the request to the backend
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), FETCH_TIMEOUT);

        const response = await fetch(`${apiUrl}/api/agents/spoke/${spokeName}/chat`, {
            method: 'POST',
            headers: forwardHeaders,
            body: body,
            signal: controller.signal,
        });

        clearTimeout(timeoutId);

        // Forward the response
        const responseText = await response.text();

        // Try to parse as JSON, otherwise return as text
        try {
            const data = JSON.parse(responseText);
            return NextResponse.json(data, { status: response.status });
        } catch {
            return new NextResponse(responseText, {
                status: response.status,
                headers: { 'Content-Type': 'text/plain' }
            });
        }

    } catch (error: any) {
        console.error('Spoke chat proxy error:', error);

        if (error.name === 'AbortError') {
            return NextResponse.json(
                { error: 'Request timeout - file may be too large' },
                { status: 504 }
            );
        }

        return NextResponse.json(
            { error: error.message || 'Failed to connect to backend' },
            { status: 502 }
        );
    }
}
