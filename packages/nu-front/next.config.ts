import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    const dataApi = process.env.DATA_API_URL || "http://localhost:8000";
    const gameApi = process.env.GAME_API_URL || "http://localhost:8001";
    return [
      { source: "/api/:path*", destination: `${dataApi}/api/:path*` },
      { source: "/game/:path*", destination: `${gameApi}/game/:path*` },
      { source: "/stream/:path*", destination: `${gameApi}/stream/:path*` },
    ];
  },
};

export default nextConfig;
