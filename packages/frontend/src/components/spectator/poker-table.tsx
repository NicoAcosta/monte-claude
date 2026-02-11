"use client"

import { useState, useEffect, useRef } from "react"
import type { SpectatorState, RecentAction } from "@/lib/types"
import type { AnimationPhase } from "@/hooks/use-replay-queue"
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
  animationPhase?: AnimationPhase
  lastAction?: RecentAction | null
}

export function PokerTable({
  state,
  dealing,
  timerText,
  timerUrgent,
  playerComments,
  animationPhase,
  lastAction,
}: PokerTableProps) {
  const playerCount = state.players.length
  const layout =
    SEAT_LAYOUTS[playerCount] || SEAT_LAYOUTS[Math.min(playerCount, 8)]

  // Track fold animation
  const [foldingPlayerId, setFoldingPlayerId] = useState<number | null>(null)

  useEffect(() => {
    if (lastAction?.action === "fold") {
      const foldedPlayer = state.players.find((p) => p.name === lastAction.player)
      if (foldedPlayer) {
        setFoldingPlayerId(foldedPlayer.id)
        const timer = setTimeout(() => setFoldingPlayerId(null), 800)
        return () => clearTimeout(timer)
      }
    }
  }, [lastAction, state.players])

  // Track previous community card count for staggered reveal
  const prevCardCountRef = useRef(state.community_cards.length)
  const prevCardCount = prevCardCountRef.current
  useEffect(() => {
    prevCardCountRef.current = state.community_cards.length
  }, [state.community_cards.length])

  return (
    <div className="poker-table">
      <div className="table-felt" />

      {/* Center: community cards + pot */}
      <div className="absolute left-1/2 top-1/2 z-[2] flex -translate-x-1/2 -translate-y-1/2 flex-col items-center gap-2.5">
        <CommunityCards
          cards={state.community_cards}
          dealing={dealing}
          animationPhase={animationPhase}
          prevCardCount={prevCardCount}
        />
        <PotDisplay pot={state.pot} sidePots={state.side_pots} players={state.players} />
      </div>

      {/* Player seats */}
      {state.players.map((player, i) => {
        const pos = layout?.[i] || { top: 50, left: 50 }
        const isActionPlayer = lastAction?.player === player.name
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
            isFolding={foldingPlayerId === player.id}
            actionLabel={
              isActionPlayer && animationPhase === "action"
                ? formatActionLabel(lastAction!)
                : null
            }
          />
        )
      })}
    </div>
  )
}

function formatActionLabel(action: RecentAction): string {
  const name = action.action.toUpperCase()
  if (action.amount && action.amount > 0) {
    return `${name} ${action.amount}`
  }
  return name
}
