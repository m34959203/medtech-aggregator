import type { NextConfig } from "next";

// Бэкенд в docker-сети; на клиенте /api/* проксируется сюда же Next-ом (one-origin).
const BACKEND = process.env.INTERNAL_API_URL || "http://localhost:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${BACKEND}/api/:path*` },
      { source: "/health", destination: `${BACKEND}/health` },
      // Питч-деск МедЦена (статический self-contained HTML в public/deck/)
      { source: "/deck", destination: "/deck/index.html" },
    ];
  },
};

export default nextConfig;
