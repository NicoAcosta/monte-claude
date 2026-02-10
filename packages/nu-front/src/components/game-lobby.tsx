"use client"

import { usePoll } from "@/hooks/use-poll"
import { ConnectionStatus } from "@/components/connection-status"
import { GameCard } from "@/components/game-card"
import { StreamCard } from "@/components/stream-card"
import type { Game, Stream, GameListResponse, StreamListResponse } from "@/lib/types"

export function GameLobby({
  initialGames,
  initialStreams,
}: {
  initialGames: Game[]
  initialStreams: Stream[]
}) {
  const { data: gamesData, status } = usePoll<GameListResponse>(
    "/api/games",
    3000
  )
  const { data: streamsData } = usePoll<StreamListResponse>(
    "/api/streams",
    3000
  )

  const games = gamesData?.games ?? initialGames
  const streams = streamsData?.streams ?? initialStreams

  return (
    <div className="mx-auto max-w-5xl px-6 py-12">
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="font-display text-3xl font-bold text-mc-white">
            Live Games
          </h1>
          <p className="mt-1 text-sm text-mc-white/40">
            {games.length} {games.length === 1 ? "game" : "games"} active
          </p>
        </div>
        <ConnectionStatus status={status} />
      </div>

      {/* Games grid */}
      {games.length > 0 ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {games.map((game, i) => (
            <GameCard key={game.id} game={game} index={i} />
          ))}
        </div>
      ) : (
        <div className="rounded-xl border border-white/5 bg-navy-light/50 px-8 py-16 text-center">
          <p className="text-lg text-mc-white/30">No active games</p>
          <p className="mt-2 text-sm text-mc-white/20">
            Games will appear here when agents start playing.
          </p>
        </div>
      )}

      {/* Streams */}
      {streams.length > 0 && (
        <div className="mt-16">
          <h2 className="mb-6 font-display text-2xl font-bold text-mc-white">
            Live Streams
          </h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {streams.map((stream, i) => (
              <StreamCard key={stream.id} stream={stream} index={i} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
