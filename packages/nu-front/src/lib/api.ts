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

async function fetchJson<T>(url: string, revalidate?: number): Promise<T> {
  const res = await fetch(url, {
    next: revalidate !== undefined ? { revalidate } : undefined,
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

export function fetchGames() {
  return fetchJson<GameListResponse>(`${DATA_API}/api/games`, 3)
}

export function fetchStreams() {
  return fetchJson<StreamListResponse>(`${DATA_API}/api/streams`, 5)
}

export function fetchLeaderboard(limit = 50, offset = 0) {
  return fetchJson<LeaderboardResponse>(
    `${DATA_API}/api/leaderboard?limit=${limit}&offset=${offset}`,
    15
  )
}

export function fetchRecentHands(limit = 20, offset = 0) {
  return fetchJson<RecentHandsResponse>(
    `${DATA_API}/api/recent-hands?limit=${limit}&offset=${offset}`,
    15
  )
}

export async function fetchPlayerStats(
  username: string
): Promise<PlayerStats | null> {
  const res = await fetch(
    `${DATA_API}/api/stats/${encodeURIComponent(username)}`,
    { next: { revalidate: 30 } }
  )
  if (res.status === 404) return null
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
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
