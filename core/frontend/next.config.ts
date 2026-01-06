/** @type {import('next').NextConfig} */
const nextConfig = {
  // Increase body size limit for file uploads
  experimental: {
    serverActions: {
      bodySizeLimit: '100mb',
    },
    proxyTimeout: 300000, // 5 minutes (in ms)
  },
  // Server external packages for proper proxying
  serverExternalPackages: [],
  async rewrites() {
    // In Docker: use backend service name (http://backend:8000)
    // Local dev: use localhost:8000
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

    return [
      {
        source: '/api/:path*',
        destination: `${apiUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;


