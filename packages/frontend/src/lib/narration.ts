import type { SpectatorState } from "./types"
import { cardToSpokenName, cardsToSpokenList, formatChips } from "./format"

export type AudioChannel = "commentator" | "playerComment"

export interface GameEvent {
  type: "new_hand" | "action" | "community" | "showdown" | "hand_complete" | "game_over"
  narration: string
  priority: number
  soundEffect?: "deal" | "chip" | "allin" | "fold" | "check"
  channel: AudioChannel
}

function getPlayerName(state: SpectatorState, playerId: number): string {
  return state.players.find((p) => p.id === playerId)?.name ?? `Player ${playerId}`
}

export function detectGameEvents(
  prev: SpectatorState,
  next: SpectatorState,
): GameEvent[] {
  const events: GameEvent[] = []

  // New hand
  if (next.hand_number > prev.hand_number) {
    const dealer = getPlayerName(next, next.dealer)
    events.push({
      type: "new_hand",
      narration: `Hand ${next.hand_number} begins. ${dealer} is the dealer.`,
      priority: 5,
      soundEffect: "deal",
      channel: "commentator",
    })
  }

  // New actions — compare recent_actions length
  // Actions only append within a hand, and reset on new hand
  if (next.hand_number === prev.hand_number) {
    const prevCount = prev.recent_actions.length
    const nextCount = next.recent_actions.length
    if (nextCount > prevCount) {
      const newActions = next.recent_actions.slice(prevCount)
      for (const a of newActions) {
        const name = a.player
        let text: string
        let sound: GameEvent["soundEffect"] = "chip"
        let priority = 3

        switch (a.action) {
          case "fold":
            text = `${name} folds.`
            sound = "fold"
            break
          case "check":
            text = `${name} checks.`
            sound = "check"
            break
          case "call":
            text = a.amount
              ? `${name} calls ${formatChips(a.amount)}.`
              : `${name} calls.`
            break
          case "bet":
            text = `${name} bets ${formatChips(a.amount ?? 0)}.`
            break
          case "raise":
            text = `${name} raises to ${formatChips(a.amount ?? 0)}.`
            priority = 4
            break
          case "all_in":
            text = a.amount
              ? `${name} goes all in! ${formatChips(a.amount)} chips.`
              : `${name} goes all in!`
            priority = 5
            sound = "allin"
            break
          default:
            text = `${name} ${a.action}.`
        }

        events.push({ type: "action", narration: text, priority, soundEffect: sound, channel: "commentator" })

        if (a.comment) {
          events.push({
            type: "action",
            narration: `${name} says: ${a.comment}`,
            priority: 2,
            channel: "playerComment",
          })
        }
      }
    }
  }

  // Community cards revealed
  if (next.community_cards.length > prev.community_cards.length) {
    const prevLen = prev.community_cards.length
    const newCards = next.community_cards.slice(prevLen)

    let text: string
    if (prevLen === 0 && newCards.length >= 3) {
      text = `The flop: ${cardsToSpokenList(newCards.slice(0, 3))}.`
    } else if (prevLen === 3 && newCards.length >= 1) {
      text = `The turn: ${cardToSpokenName(newCards[0])}.`
    } else if (prevLen === 4 && newCards.length >= 1) {
      text = `The river: ${cardToSpokenName(newCards[0])}.`
    } else {
      text = `Cards revealed: ${cardsToSpokenList(newCards)}.`
    }

    events.push({ type: "community", narration: text, priority: 6, soundEffect: "deal", channel: "commentator" })
  }

  // Showdown
  if (
    next.phase === "showdown" &&
    prev.phase !== "showdown" &&
    prev.phase !== "complete"
  ) {
    events.push({ type: "showdown", narration: "Showdown!", priority: 7, channel: "commentator" })
  }

  // Hand complete — detect winner by chip gains
  if (next.phase === "complete" && prev.phase !== "complete") {
    const prevPot = prev.pot
    let winner: string | null = null
    let winnerPlayer: typeof next.players[number] | undefined
    for (const np of next.players) {
      const pp = prev.players.find((p) => p.id === np.id)
      if (pp && np.chips > pp.chips) {
        winner = np.name
        winnerPlayer = np
        break
      }
    }
    if (winner && prevPot > 0) {
      const activePlayers = next.players.filter((p) => !p.is_folded)
      const foldWin = activePlayers.length === 1

      let narration: string
      if (foldWin) {
        narration = `${winner} wins ${formatChips(prevPot)} — all others folded.`
      } else if (winnerPlayer?.cards.length === 2) {
        const cardStr = cardsToSpokenList(winnerPlayer.cards)
        narration = `${winner} wins ${formatChips(prevPot)} showing ${cardStr}!`
      } else {
        narration = `${winner} wins the pot of ${formatChips(prevPot)}!`
      }

      events.push({
        type: "hand_complete",
        narration,
        priority: 8,
        channel: "commentator",
      })
    } else if (winner) {
      events.push({
        type: "hand_complete",
        narration: `${winner} wins the hand!`,
        priority: 8,
        channel: "commentator",
      })
    }
  }

  // Game over
  if (next.game_over && !prev.game_over && next.winner) {
    events.push({
      type: "game_over",
      narration: `Game over! ${next.winner} wins the game!`,
      priority: 10,
      channel: "commentator",
    })
  }

  return events
}
