import { cacheLife, cacheTag } from "next/cache"
import type {
  GameListResponse,
  StreamListResponse,
  LeaderboardResponse,
  RecentHandsResponse,
  PlayerStats,
  SpectatorState,
} from "./types"

const DATA_API = process.env.DATA_API_URL || "http://localhost:8000"
const GAME_API = process.env.GAME_API_URL || "http://localhost:8001"

export async function fetchGames(): Promise<GameListResponse> {
  "use cache"
  cacheLife({ revalidate: 3 })
  cacheTag("games")
  try {
    const res = await fetch(`${DATA_API}/api/games`)
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
    return res.json()
  } catch {
    return { games: [] } as GameListResponse
  }
}

export async function fetchStreams(): Promise<StreamListResponse> {
  "use cache"
  cacheLife({ revalidate: 5 })
  cacheTag("streams")
  try {
    const res = await fetch(`${DATA_API}/api/streams`)
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
    return res.json()
  } catch {
    return { streams: [] } as StreamListResponse
  }
}

export async function fetchLeaderboard(limit = 50, offset = 0): Promise<LeaderboardResponse> {
  "use cache"
  cacheLife("minutes")
  cacheTag("leaderboard")
  try {
    const res = await fetch(
      `${DATA_API}/api/leaderboard?limit=${limit}&offset=${offset}`
    )
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
    return res.json()
  } catch {
    return { players: [], total: 0 }
  }
}

export async function fetchRecentHands(limit = 20, offset = 0): Promise<RecentHandsResponse> {
  "use cache"
  cacheLife("minutes")
  cacheTag("recent-hands")
  try {
    const res = await fetch(
      `${DATA_API}/api/recent-hands?limit=${limit}&offset=${offset}`
    )
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
    return res.json()
  } catch {
    return { hands: [], total: 0 } as RecentHandsResponse
  }
}

export async function fetchPlayerStats(
  username: string
): Promise<PlayerStats | null> {
  "use cache"
  cacheLife("minutes")
  cacheTag("player-stats", username)
  try {
    const res = await fetch(
      `${DATA_API}/api/stats/${encodeURIComponent(username)}`
    )
    if (res.status === 404) return null
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
    return res.json()
  } catch {
    return null
  }
}

export async function fetchSpectatorState(
  gameId: string
): Promise<SpectatorState | null> {
  const res = await fetch(`${GAME_API}/api/games/${gameId}/spectator`, {
    cache: "no-store",
  })
  if (res.status === 404) return null
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

export async function fetchStreamState(
  streamId: string
): Promise<SpectatorState | null> {
  const res = await fetch(`${GAME_API}/api/streams/${streamId}/data`, {
    cache: "no-store",
  })
  if (res.status === 404) return null
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}
