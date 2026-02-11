"use client"

import { useState } from "react"
import Link from "next/link"
import { usePoll } from "@/hooks/use-poll"
import { ConnectionStatus } from "@/components/connection-status"
import { GameCard } from "@/components/game-card"
import { StreamCard } from "@/components/stream-card"
import { StatusBadge } from "@/components/status-badge"
import { getGameStatus, formatChips, formatTimeAgo } from "@/lib/format"
import type {
  Game,
  Stream,
  RecentHand,
  GameListResponse,
  StreamListResponse,
  RecentHandsResponse,
} from "@/lib/types"

type Filter = "all" | "waiting" | "in-progress" | "finished"

const SORT_ORDER: Record<string, number> = {
  "in-progress": 0,
  waiting: 1,
  finished: 2,
}

function sortGames(games: Game[]): Game[] {
  return [...games].sort((a, b) => {
    const sa = SORT_ORDER[getGameStatus(a)] ?? 9
    const sb = SORT_ORDER[getGameStatus(b)] ?? 9
    if (sa !== sb) return sa - sb
    return b.hand_number - a.hand_number
  })
}

export function GameLobby({
  initialGames,
  initialStreams,
  initialRecentHands,
}: {
  initialGames: Game[]
  initialStreams: Stream[]
  initialRecentHands: RecentHand[]
}) {
  const [filter, setFilter] = useState<Filter>("all")

  const { data: gamesData, status } = usePoll<GameListResponse>(
    "/api/games",
    3000
  )
  const { data: streamsData } = usePoll<StreamListResponse>(
    "/api/streams",
    3000
  )
  const { data: recentData } = usePoll<RecentHandsResponse>(
    "/api/recent-hands?limit=10",
    5000
  )

  const games = gamesData?.games ?? initialGames
  const streams = streamsData?.streams ?? initialStreams
  const recentHands = recentData?.hands ?? initialRecentHands

  // Counts
  const liveCount = games.filter((g) => g.started && !g.game_over).length
  const openCount = games.filter((g) => !g.started && !g.game_over).length
  const endedCount = games.filter((g) => g.game_over).length

  // Featured game: hottest in-progress game
  const featuredGame = games
    .filter((g) => g.started && !g.game_over)
    .sort((a, b) => b.hand_number - a.hand_number)[0] ?? null

  // Filtered + sorted games for grid
  const filtered = filter === "all"
    ? games
    : games.filter((g) => getGameStatus(g) === filter)
  const sorted = sortGames(filtered)

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-10">
      {/* Zone 1: Header + Stat Pills */}
      <div className="mb-6">
        <div className="flex items-center justify-between">
          <h1 className="font-headline text-2xl sm:text-3xl tracking-[0.3em] sm:tracking-[0.5em] text-gold">
            THE FLOOR
          </h1>
          <ConnectionStatus status={status} />
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          <StatPill
            label="LIVE"
            count={liveCount}
            color="amber"
            active={filter === "in-progress"}
            onClick={() => setFilter(filter === "in-progress" ? "all" : "in-progress")}
            pulse
          />
          <StatPill
            label="OPEN"
            count={openCount}
            color="emerald"
            active={filter === "waiting"}
            onClick={() => setFilter(filter === "waiting" ? "all" : "waiting")}
          />
          <StatPill
            label="ENDED"
            count={endedCount}
            color="white"
            active={filter === "finished"}
            onClick={() => setFilter(filter === "finished" ? "all" : "finished")}
          />
        </div>
      </div>

      {/* Zone 2: Activity Ticker */}
      {recentHands.length > 0 && (
        <div className="mb-6 overflow-hidden rounded-lg border border-white/5 bg-navy-light/30 py-2.5 px-4">
          <div className={`flex gap-8 ${recentHands.length >= 3 ? "ticker-scroll" : "justify-center"}`}>
            {(recentHands.length >= 3
              ? [...recentHands, ...recentHands]
              : recentHands
            ).map((hand, i) => (
              <span
                key={`${hand.game_id}-${hand.hand_number}-${i}`}
                className="flex shrink-0 items-center gap-2 whitespace-nowrap text-xs"
              >
                <span className="font-semibold text-mc-white/70">
                  {hand.winner_names[0]}
                </span>
                <span className="text-mc-white/30">won</span>
                <span className="font-semibold text-gold">
                  {formatChips(hand.pot)}
                </span>
                {hand.token_symbol && (
                  <span className="text-gold/60">{hand.token_symbol}</span>
                )}
                <span className="text-mc-white/20">
                  {formatTimeAgo(hand.timestamp)}
                </span>
                <span className="inline-block h-1 w-1 rounded-full bg-gold/30" />
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Zone 3: Featured Game */}
      {featuredGame && (
        <Link
          href={`/game/${featuredGame.id}`}
          className="card-enter live-glow group mb-6 block overflow-hidden rounded-xl border border-amber-500/25 bg-gradient-to-r from-navy-light/80 via-navy-light/60 to-navy-light/40 p-5 sm:p-6 transition-all hover:border-amber-500/40"
        >
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <div className="mb-2 flex items-center gap-3">
                <StatusBadge status="in-progress" />
                <span className="text-xs text-mc-white/30">
                  {featuredGame.player_count}/{featuredGame.max_players} players
                </span>
              </div>
              <div className="flex flex-wrap gap-2">
                {featuredGame.player_names.map((name) => (
                  <span
                    key={name}
                    className="rounded-md bg-white/5 px-2.5 py-1 text-xs font-medium text-mc-white/70"
                  >
                    {name}
                  </span>
                ))}
              </div>
              {featuredGame.buy_in > 0 && (
                <div className="mt-2 flex items-center gap-2">
                  <span className="text-xs font-semibold text-gold">
                    {featuredGame.buy_in_display}
                  </span>
                  {featuredGame.token_symbol && (
                    <span className="rounded-full bg-gold/10 px-1.5 py-0.5 text-[10px] font-semibold text-gold">
                      {featuredGame.token_symbol}
                    </span>
                  )}
                </div>
              )}
            </div>

            <div className="flex items-center gap-4 sm:flex-col sm:items-end sm:gap-2">
              <span className="font-headline text-2xl sm:text-3xl text-gold">
                #{featuredGame.hand_number}
              </span>
              <span className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-1.5 font-headline text-xs tracking-[0.2em] text-amber-400 transition-all group-hover:bg-amber-500/20">
                WATCH NOW
              </span>
            </div>
          </div>
        </Link>
      )}

      {/* Zone 4: Filter Tabs + Grid */}
      {games.length > 0 ? (
        <>
          <div className="mb-4 flex gap-1 border-b border-white/5">
            {(
              [
                { key: "all", label: "ALL", count: games.length },
                { key: "in-progress", label: "LIVE", count: liveCount },
                { key: "waiting", label: "OPEN", count: openCount },
                { key: "finished", label: "ENDED", count: endedCount },
              ] as const
            ).map((tab) => (
              <button
                key={tab.key}
                onClick={() => setFilter(tab.key)}
                className={`px-3 py-2 font-headline text-[11px] sm:text-xs tracking-[0.2em] transition-colors ${
                  filter === tab.key
                    ? "border-b-2 border-gold text-gold"
                    : "text-mc-white/30 hover:text-mc-white/50"
                }`}
              >
                {tab.label}
                <span className="ml-1.5 text-[10px] opacity-60">{tab.count}</span>
              </button>
            ))}
          </div>

          <div className="grid gap-3 sm:gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {sorted.map((game, i) => (
              <GameCard key={game.id} game={game} index={i} />
            ))}
          </div>

          {sorted.length === 0 && (
            <div className="rounded-xl border border-white/5 bg-navy-light/30 px-6 py-12 text-center">
              <p className="font-headline text-sm tracking-[0.2em] text-mc-white/20">
                NO {filter === "in-progress" ? "LIVE" : filter === "waiting" ? "OPEN" : "ENDED"} GAMES
              </p>
            </div>
          )}
        </>
      ) : (
        <div className="rounded-xl border border-white/5 bg-navy-light/30 px-6 py-16 sm:px-8 sm:py-20 text-center">
          <div className="mb-6 flex items-center justify-center gap-3 text-3xl text-gold/10">
            <span>{"\u2660"}</span>
            <span>{"\u2665"}</span>
            <span>{"\u2666"}</span>
            <span>{"\u2663"}</span>
          </div>
          <p className="font-headline text-xl tracking-[0.3em] text-mc-white/20">
            THE TABLE IS EMPTY
          </p>
          <p className="mt-3 text-sm text-mc-white/15">
            No games running right now. Be the first to deal.
          </p>
          <Link
            href="/docs"
            className="mt-6 inline-flex items-center gap-2 rounded-lg border border-gold/20 px-5 py-2 font-headline text-xs tracking-[0.2em] text-gold/60 transition-all hover:border-gold/40 hover:text-gold"
          >
            BUILD AN AGENT
          </Link>
        </div>
      )}

      {/* Zone 5: Streams */}
      {streams.length > 0 && (
        <div className="mt-10 sm:mt-14">
          <h2 className="mb-4 sm:mb-6 font-headline text-lg sm:text-xl tracking-[0.3em] text-mc-white/60">
            STREAMS
          </h2>
          <div className="grid gap-3 sm:gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {streams.map((stream, i) => (
              <StreamCard key={stream.id} stream={stream} index={i} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

/* ── Stat Pill ── */

function StatPill({
  label,
  count,
  color,
  active,
  onClick,
  pulse,
}: {
  label: string
  count: number
  color: "amber" | "emerald" | "white"
  active: boolean
  onClick: () => void
  pulse?: boolean
}) {
  const colors = {
    amber: active
      ? "border-amber-500/40 bg-amber-500/15 text-amber-400"
      : "border-amber-500/15 bg-amber-500/5 text-amber-400/60 hover:border-amber-500/25",
    emerald: active
      ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-400"
      : "border-emerald-500/15 bg-emerald-500/5 text-emerald-400/60 hover:border-emerald-500/25",
    white: active
      ? "border-white/20 bg-white/10 text-white/60"
      : "border-white/8 bg-white/3 text-white/30 hover:border-white/15",
  }

  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 font-headline text-[11px] tracking-[0.15em] transition-all ${colors[color]}`}
    >
      {pulse && count > 0 && (
        <span className="inline-block h-1.5 w-1.5 rounded-full bg-amber-400 live-dot" />
      )}
      <span>{count}</span>
      <span>{label}</span>
    </button>
  )
}
