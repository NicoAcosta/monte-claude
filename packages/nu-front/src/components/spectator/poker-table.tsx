import type { SpectatorState } from "@/lib/types"
import { SEAT_LAYOUTS } from "./seat-layouts"
import { CommunityCards } from "./community-cards"
import { PotDisplay } from "./pot-display"
import { PlayerSeat } from "./player-seat"

interface PokerTableProps {
  state: SpectatorState
  dealing: boolean
  timerText: string | null
  timerUrgent: boolean
  playerComments: Record<string, string>
}

export function PokerTable({
  state,
  dealing,
  timerText,
  timerUrgent,
  playerComments,
}: PokerTableProps) {
  const playerCount = state.players.length
  const layout =
    SEAT_LAYOUTS[playerCount] || SEAT_LAYOUTS[Math.min(playerCount, 8)]

  return (
    <div className="poker-table">
      <div className="table-felt" />

      {/* Center: community cards + pot */}
      <div className="absolute left-1/2 top-1/2 z-[2] flex -translate-x-1/2 -translate-y-1/2 flex-col items-center gap-2.5">
        <CommunityCards cards={state.community_cards} dealing={dealing} />
        <PotDisplay pot={state.pot} sidePots={state.side_pots} />
      </div>

      {/* Player seats */}
      {state.players.map((player, i) => {
        const pos = layout?.[i] || { top: 50, left: 50 }
        return (
          <PlayerSeat
            key={player.id}
            player={player}
            position={pos}
            isCurrentTurn={state.current_turn === player.id}
            isDealer={state.dealer === player.id}
            isSmallBlind={state.small_blind_player === player.id}
            isBigBlind={state.big_blind_player === player.id}
            timerText={state.current_turn === player.id ? timerText : null}
            timerUrgent={timerUrgent}
            comment={playerComments[player.name] || null}
            dealing={dealing}
          />
        )
      })}
    </div>
  )
}
