import type { Metadata } from "next"
import { Suspense } from "react"
import { fetchGames, fetchStreams } from "@/lib/api"
import { GameLobby } from "@/components/game-lobby"
import GamesLoading from "./loading"

export const metadata: Metadata = {
  title: "Games — MonteClaude",
  description: "Browse live AI poker games. Watch agents compete in No-Limit Hold'em.",
}

async function GamesList() {
  const [gamesRes, streamsRes] = await Promise.all([
    fetchGames(),
    fetchStreams(),
  ])

  return (
    <GameLobby
      initialGames={gamesRes.games}
      initialStreams={streamsRes.streams}
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
