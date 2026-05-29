/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@ai-video-editor/shared-types"],
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: process.env.API_URL || "http://localhost:4000/api/:path*",
      },
    ];
  },
};

module.exports = nextConfig;
