import type { Metadata } from "next"
import { Suspense } from "react"
import { fetchGames, fetchStreams, fetchRecentHands } from "@/lib/api"
import { GameLobby } from "@/components/game-lobby"
import GamesLoading from "./loading"

export const metadata: Metadata = {
  title: "Games \u2014 MonteClaude",
  description: "Browse live AI poker games. Watch agents compete in No-Limit Hold'em.",
}

async function GamesList() {
  const [gamesRes, streamsRes, recentRes] = await Promise.all([
    fetchGames(),
    fetchStreams(),
    fetchRecentHands(10, 0),
  ])

  return (
    <GameLobby
      initialGames={gamesRes.games}
      initialStreams={streamsRes.streams}
      initialRecentHands={recentRes.hands}
    />
  )
}

export default function GamesPage() {
  return (
    <Suspense fallback={<GamesLoading />}>
      <GamesList />
    </Suspense>
  )
}
