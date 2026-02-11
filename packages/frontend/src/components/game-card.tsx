import { memo } from "react"
import Link from "next/link"
import { StatusBadge } from "@/components/status-badge"
import { getGameStatus, formatChips } from "@/lib/format"
import type { Game } from "@/lib/types"

type GameStatus = "waiting" | "in-progress" | "finished"

function shortId(id: string | number): string {
  const s = String(id)
  if (s.length <= 12) return s
  return `${s.slice(0, 6)}\u2026${s.slice(-4)}`
}

const CARD_STYLES: Record<GameStatus, string> = {
  "in-progress":
    "border-amber-500/25 bg-gradient-to-br from-navy-light/80 to-navy-light/40 live-glow hover:scale-[1.02] hover:border-amber-500/40",
  waiting:
    "border-emerald-500/15 bg-navy-light/50 hover:border-emerald-500/30",
  finished:
    "border-white/5 bg-navy-light/30 opacity-75 hover:opacity-90",
}

const ACCENT_STYLES: Record<GameStatus, string> = {
  "in-progress": "h-0.5 bg-gradient-to-r from-transparent via-amber-500/60 to-transparent",
  waiting: "h-0.5 border-t border-dashed border-emerald-500/20",
  finished: "hidden",
}

export const GameCard = memo(function GameCard({ game, index }: { game: Game; index: number }) {
  const status = getGameStatus(game)
  const seatsOpen = game.max_players - game.player_count

  return (
    <Link
      href={`/game/${game.id}`}
      className={`card-enter group block overflow-hidden rounded-xl border p-4 sm:p-5 transition-all duration-200 ${CARD_STYLES[status]}`}
      style={{ animationDelay: `${index * 0.06}s` }}
    >
      {/* Top accent bar */}
      <div className={ACCENT_STYLES[status]} />

      {/* Header row */}
      <div className={`${status !== "finished" ? "mt-2" : ""} mb-3 flex items-start justify-between gap-2`}>
        <h3 className="min-w-0 truncate font-display text-sm sm:text-base font-bold text-mc-white">
          Game #{shortId(game.id)}
        </h3>
        <StatusBadge status={status} />
      </div>

      {/* Player tags */}
      <div className="mb-3 flex flex-wrap gap-1.5">
        {game.player_names.map((name) => (
          <span
            key={name}
            className="rounded-md bg-white/5 px-2 py-0.5 text-[11px] sm:text-xs text-mc-white/60"
          >
            {name}
          </span>
        ))}
      </div>

      {/* Metrics row */}
      <div className="flex items-center justify-between">
        {status === "in-progress" ? (
          <>
            <span className="font-headline text-lg sm:text-xl text-gold">
              Hand #{game.hand_number}
            </span>
            <span className="text-sm font-bold text-mc-white/50">
              {game.player_count}/{game.max_players}
            </span>
          </>
        ) : status === "waiting" ? (
          <>
            <span className="text-[11px] sm:text-xs text-mc-white/30">
              Hand #{game.hand_number}
            </span>
            <span className="text-[11px] sm:text-xs font-medium text-emerald-400/80">
              {seatsOpen} {seatsOpen === 1 ? "seat" : "seats"} open
            </span>
          </>
        ) : (
          <>
            <span className="text-[11px] sm:text-xs text-mc-white/20">
              {game.hand_number} hands played
            </span>
            <span className="text-[11px] sm:text-xs text-mc-white/20">
              {game.player_count}/{game.max_players}
            </span>
          </>
        )}
      </div>

      {/* Winner */}
      {game.winner && (
        <div className="mt-2 text-xs font-semibold text-gold">
          {"\u{1F451}"} {game.winner}
        </div>
      )}

      {/* Buy-in */}
      {game.buy_in > 0 && (
        <div className="mt-2 flex items-center gap-2">
          <span className="text-xs font-semibold text-gold">
            {game.buy_in_display}
          </span>
          {game.token_symbol && (
            <span className="rounded-full bg-gold/10 px-1.5 py-0.5 text-[10px] font-semibold text-gold">
              {game.token_symbol}
            </span>
          )}
        </div>
      )}
    </Link>
  )
})
