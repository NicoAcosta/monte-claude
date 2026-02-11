import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  cacheComponents: true,
  async rewrites() {
    const dataApi = process.env.DATA_API_URL || "http://localhost:8000";
    const gameApi = process.env.GAME_API_URL || "http://localhost:8001";
    return [
      // Game API: spectator compat route (game-type agnostic)
      { source: "/api/games/:id/spectator", destination: `${gameApi}/game/:id/spectator` },
      // Game API: poker-specific routes
      { source: "/api/games/:id/state", destination: `${gameApi}/game/poker/:id/state` },
      { source: "/api/games/:id/waiting", destination: `${gameApi}/game/poker/:id/waiting` },
      { source: "/api/games/:id/escrow", destination: `${gameApi}/game/poker/:id/escrow` },
      { source: "/api/games/:id/funding", destination: `${gameApi}/game/poker/:id/funding` },
      { source: "/api/games/:id/settlement", destination: `${gameApi}/game/poker/:id/settlement` },
      { source: "/api/games/:id/offchain-settlement", destination: `${gameApi}/game/poker/:id/offchain-settlement` },
      // Game API: stream routes
      { source: "/api/streams/:id/data", destination: `${gameApi}/stream/:id/data` },
      // Data API: everything else under /api/
      { source: "/api/:path*", destination: `${dataApi}/api/:path*` },
    ];
  },
};

export default nextConfig;
