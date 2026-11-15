/** @type {import('next').NextConfig} */
const nextConfig = {
  // Allow a separate local verification server to avoid sharing .next with an
  // already-running development server or production build.
  distDir: process.env.NEXT_DIST_DIR || '.next',
  output: 'standalone',
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://backend:8000/api/:path*',
      },
    ];
  },
};

module.exports = nextConfig;
