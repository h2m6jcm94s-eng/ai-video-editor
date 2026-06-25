import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  experimental: { typedRoutes: true },
  // Watch and transpile the workspace shared-types package so changes are
  // picked up during `pnpm dev` without needing a manual Next.js restart.
  transpilePackages: ["@ai-video-editor/shared-types"],
  images: {
    remotePatterns: [{ hostname: "*.r2.cloudflarestorage.com" }],
  },
  webpack: (config) => {
    config.resolve.alias = {
      ...config.resolve.alias,
      canvas: false,
    };
    return config;
  },
};

export default nextConfig;
