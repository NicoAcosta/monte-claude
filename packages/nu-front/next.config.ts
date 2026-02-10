import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    const dataApi = process.env.DATA_API_URL || "http://localhost:8000";
    const gameApi = process.env.GAME_API_URL || "http://localhost:8001";
    return [
      { source: "/api/:path*", destination: `${dataApi}/api/:path*` },
      { source: "/game/:id/spectator/snapshots", destination: `${gameApi}/game/:id/spectator/snapshots` },
      { source: "/game/:id/:action+", destination: `${gameApi}/game/:id/:action+` },
      { source: "/stream/:id/snapshots", destination: `${gameApi}/stream/:id/snapshots` },
      { source: "/stream/:path*", destination: `${gameApi}/stream/:path*` },
    ];
  },
};

export default nextConfig;
