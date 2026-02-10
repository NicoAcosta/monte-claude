import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    const dataApi = process.env.DATA_API_URL || "http://localhost:8000";
    const gameApi = process.env.GAME_API_URL || "http://localhost:8001";
    return [
      // Game API: game writes + live state reads
      { source: "/api/games/:id/spectator/snapshots", destination: `${gameApi}/api/games/:id/spectator/snapshots` },
      { source: "/api/games/:id/spectator", destination: `${gameApi}/api/games/:id/spectator` },
      { source: "/api/games/:id/state", destination: `${gameApi}/api/games/:id/state` },
      { source: "/api/games/:id/waiting", destination: `${gameApi}/api/games/:id/waiting` },
      { source: "/api/games/:id/escrow", destination: `${gameApi}/api/games/:id/escrow` },
      { source: "/api/games/:id/funding", destination: `${gameApi}/api/games/:id/funding` },
      { source: "/api/games/:id/settlement", destination: `${gameApi}/api/games/:id/settlement` },
      { source: "/api/games/:id/offchain-settlement", destination: `${gameApi}/api/games/:id/offchain-settlement` },
      { source: "/api/streams/:id/data", destination: `${gameApi}/api/streams/:id/data` },
      { source: "/api/streams/:id/snapshots", destination: `${gameApi}/api/streams/:id/snapshots` },
      // Data API: everything else under /api/
      { source: "/api/:path*", destination: `${dataApi}/api/:path*` },
    ];
  },
};

export default nextConfig;
