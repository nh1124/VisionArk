import { NextRequest, NextResponse } from 'next/server';

/**
 * API Route handler for file operations
 * This proxies file requests to the backend with proper header forwarding
 */

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function GET(
    request: NextRequest,
    { params }: { params: Promise<{ path: string[] }> }
) {
    const { path } = await params;
    const pathStr = path.join('/');
    const url = `${BACKEND_URL}/api/files/${pathStr}`;

    const headers: HeadersInit = {};
    const authHeader = request.headers.get('Authorization');
    if (authHeader) {
        headers['Authorization'] = authHeader;
    }

    try {
        const response = await fetch(url, {
            method: 'GET',
            headers,
        });

        const data = await response.json();
        return NextResponse.json(data, { status: response.status });
    } catch (error) {
        console.error('[API Route] GET error:', error);
        return NextResponse.json({ detail: 'Proxy error' }, { status: 500 });
    }
}

export async function POST(
    request: NextRequest,
    { params }: { params: Promise<{ path: string[] }> }
) {
    const { path } = await params;
    const pathStr = path.join('/');
    const url = `${BACKEND_URL}/api/files/${pathStr}`;

    // Forward authorization header
    const headers: HeadersInit = {};
    const authHeader = request.headers.get('Authorization');
    if (authHeader) {
        headers['Authorization'] = authHeader;
    }

    // Debug logging
    console.log(`[API Route] POST /api/files/${pathStr}`);
    console.log(`[API Route] Auth header present: ${!!authHeader}`);

    try {
        // Get the body - could be FormData or JSON
        const contentType = request.headers.get('Content-Type') || '';

        let response: Response;

        if (contentType.includes('multipart/form-data')) {
            // For file uploads, forward the request body as-is
            const formData = await request.formData();

            response = await fetch(url, {
                method: 'POST',
                headers,
                body: formData,
            });
        } else {
            // For JSON requests
            const body = await request.text();
            if (contentType) {
                headers['Content-Type'] = contentType;
            }

            response = await fetch(url, {
                method: 'POST',
                headers,
                body,
            });
        }

        // Try to parse as JSON
        const text = await response.text();
        try {
            const data = JSON.parse(text);
            return NextResponse.json(data, { status: response.status });
        } catch {
            return new NextResponse(text, { status: response.status });
        }
    } catch (error) {
        console.error('[API Route] POST error:', error);
        return NextResponse.json({ detail: 'Proxy error' }, { status: 500 });
    }
}

export async function DELETE(
    request: NextRequest,
    { params }: { params: Promise<{ path: string[] }> }
) {
    const { path } = await params;
    const pathStr = path.join('/');
    const url = `${BACKEND_URL}/api/files/${pathStr}`;

    const headers: HeadersInit = {};
    const authHeader = request.headers.get('Authorization');
    if (authHeader) {
        headers['Authorization'] = authHeader;
    }

    try {
        const response = await fetch(url, {
            method: 'DELETE',
            headers,
        });

        const data = await response.json();
        return NextResponse.json(data, { status: response.status });
    } catch (error) {
        console.error('[API Route] DELETE error:', error);
        return NextResponse.json({ detail: 'Proxy error' }, { status: 500 });
    }
}
