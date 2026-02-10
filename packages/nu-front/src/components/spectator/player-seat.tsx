import { CardDisplay, CardBack } from "@/components/card-display"
import { formatChips } from "@/lib/format"
import type { SpectatorPlayer } from "@/lib/types"
import type { SeatPosition } from "./seat-layouts"

interface PlayerSeatProps {
  player: SpectatorPlayer
  position: SeatPosition
  isCurrentTurn: boolean
  isDealer: boolean
  isSmallBlind: boolean
  isBigBlind: boolean
  timerText: string | null
  timerUrgent: boolean
  comment: string | null
  dealing: boolean
  actionLabel?: string | null
}

export function PlayerSeat({
  player,
  position,
  isCurrentTurn,
  isDealer,
  isSmallBlind,
  isBigBlind,
  timerText,
  timerUrgent,
  comment,
  dealing,
  actionLabel,
}: PlayerSeatProps) {
  const stateClass = player.is_folded
    ? "folded"
    : player.is_resigned
      ? "resigned"
      : player.is_all_in
        ? "all-in"
        : isCurrentTurn
          ? "current-turn"
          : ""

  return (
    <div
      className={`player-seat ${stateClass} absolute z-[3] flex flex-col items-center gap-1`}
      style={{
        top: `${position.top}%`,
        left: `${position.left}%`,
        transform: "translate(-50%, -50%)",
      }}
    >
      {/* Hole cards */}
      <div className="flex gap-0.5">
        {player.cards && player.cards.length > 0 ? (
          player.is_folded ? (
            <>
              <CardBack small dealing={dealing} />
              <CardBack small dealing={dealing} />
            </>
          ) : (
            player.cards.map((c, i) => (
              <CardDisplay key={i} card={c} small dealing={dealing} />
            ))
          )
        ) : (
          <>
            <CardBack small dealing={dealing} />
            <CardBack small dealing={dealing} />
          </>
        )}
      </div>

      {/* Player info box */}
      <div
        className="player-info min-w-[100px] rounded-lg border-2 border-transparent bg-black/55 px-3 py-1.5 text-center backdrop-blur-sm"
        style={{ transition: "border-color .35s cubic-bezier(.4,0,.2,1), box-shadow .35s cubic-bezier(.4,0,.2,1)" }}
      >
        <div className="truncate text-[13px] font-bold text-white">
          {player.name}
        </div>
        <div className="text-xs font-semibold text-[#27ae60]">
          {formatChips(player.chips)}
        </div>
        {player.current_bet > 0 && (
          <div className="mt-0.5 text-[11px] text-[#a17e2f]">
            Bet: {formatChips(player.current_bet)}
          </div>
        )}

        {/* Badges */}
        <div className="mt-0.5 flex flex-wrap justify-center gap-1">
          {isDealer && (
            <span className="rounded-full bg-[#d4a843] px-1.5 py-px text-[9px] font-bold uppercase tracking-wide text-[#1a1a1a]">
              D
            </span>
          )}
          {isSmallBlind && (
            <span className="rounded-full bg-[#2980b9] px-1.5 py-px text-[9px] font-bold uppercase text-white">
              SB
            </span>
          )}
          {isBigBlind && (
            <span className="rounded-full bg-[#8e44ad] px-1.5 py-px text-[9px] font-bold uppercase text-white">
              BB
            </span>
          )}
          {player.is_all_in && (
            <span className="rounded-full bg-[#e74c3c] px-1.5 py-px text-[9px] font-bold uppercase text-white">
              ALL-IN
            </span>
          )}
          {player.is_folded && (
            <span className="rounded-full bg-white/15 px-1.5 py-px text-[9px] font-bold uppercase text-[#8a9a7c]">
              FOLD
            </span>
          )}
          {player.is_resigned && (
            <span className="rounded-full bg-[#e74c3c]/50 px-1.5 py-px text-[9px] font-bold uppercase text-white">
              QUIT
            </span>
          )}
          {player.extensions_remaining > 0 && (
            <span className="rounded-full bg-[#2980b9]/50 px-1.5 py-px text-[9px] font-bold uppercase text-white">
              +{player.extensions_remaining}
            </span>
          )}
        </div>
      </div>

      {/* Timer */}
      {timerText && isCurrentTurn && (
        <div
          className={`text-sm font-bold tabular-nums ${
            timerUrgent
              ? "text-[#e74c3c]"
              : "text-[#d4a843]"
          }`}
          style={
            timerUrgent
              ? { animation: "timer-pulse 0.6s ease-in-out infinite" }
              : undefined
          }
        >
          {timerText}
        </div>
      )}

      {/* Action label overlay */}
      {actionLabel && (
        <div className="action-label">
          {actionLabel}
        </div>
      )}

      {/* Speech bubble */}
      {comment && (
        <div className="speech-bubble">
          {comment}
        </div>
      )}
    </div>
  )
}
