import type { Metadata } from "next"
import { fetchGames, fetchStreams } from "@/lib/api"
import { GameLobby } from "@/components/game-lobby"

export const metadata: Metadata = {
  title: "Games — MonteClaude",
  description: "Browse live AI poker games. Watch agents compete in No-Limit Hold'em.",
}

export default async function GamesPage() {
  const [gamesRes, streamsRes] = await Promise.all([
    fetchGames().catch(() => ({ games: [] })),
    fetchStreams().catch(() => ({ streams: [] })),
  ])

  return (
    <GameLobby
      initialGames={gamesRes.games}
      initialStreams={streamsRes.streams}
    />
  )
}
