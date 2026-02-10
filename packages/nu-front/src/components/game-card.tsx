import { memo } from "react"
import Link from "next/link"
import { StatusBadge } from "@/components/status-badge"
import { getGameStatus, formatChips } from "@/lib/format"
import type { Game } from "@/lib/types"

export const GameCard = memo(function GameCard({ game, index }: { game: Game; index: number }) {
  const status = getGameStatus(game)

  return (
    <Link
      href={`/game/${game.id}`}
      className="group block rounded-xl border border-white/8 bg-navy-light/60 p-5 transition-all hover:border-white/15 hover:shadow-lg"
      style={{ animationDelay: `${index * 0.05}s` }}
    >
      {/* Top row */}
      <div className="mb-3 flex items-start justify-between">
        <h3 className="font-display text-base font-bold text-mc-white">
          Game #{game.id}
        </h3>
        <StatusBadge status={status} />
      </div>

      {/* Player tags */}
      <div className="mb-4 flex flex-wrap gap-1.5">
        {game.player_names.map((name) => (
          <span
            key={name}
            className="rounded-md bg-white/5 px-2 py-0.5 text-xs text-mc-white/60"
          >
            {name}
          </span>
        ))}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between text-xs text-mc-white/30">
        <span>Hand #{game.hand_number}</span>
        <span>
          {game.player_count}/{game.max_players} players
        </span>
      </div>

      {/* Winner */}
      {game.winner && (
        <div className="mt-2 text-xs font-semibold text-gold">
          Winner: {game.winner}
        </div>
      )}

      {/* Buy-in */}
      {game.buy_in > 0 && (
        <div className="mt-1 text-xs text-mc-white/20">
          Buy-in: {game.buy_in_display}
          {game.token_symbol ? ` ${game.token_symbol}` : ""}
        </div>
      )}
    </Link>
  )
})
