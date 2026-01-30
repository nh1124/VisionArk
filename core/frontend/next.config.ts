/** @type {import('next').NextConfig} */
const nextConfig = {
  // Hide Next.js development indicator
  devIndicators: false,
  // Increase body size limit for file uploads
  experimental: {
    serverActions: {
      bodySizeLimit: '100mb',
    },
    proxyTimeout: 300000, // 5 minutes (in ms)
  },
  // Server external packages for proper proxying
  serverExternalPackages: [],
  transpilePackages: ['mermaid'],
  async rewrites() {
    // In Docker: use backend service name (http://backend:8000)
    // Local dev: use localhost:8000
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    // const apiUrl = 'http://host.docker.internal:8000';
    // const apiUrl = 'http://172.21.0.4:8000';

    console.log(`[Next.js Config] Configuring API rewrites to: ${apiUrl}`);

    return [
      {
        source: '/api/:path*',
        destination: `${apiUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;


