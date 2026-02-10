"use client"

import { useRef, useState, useEffect } from "react"
import type { SpectatorState } from "@/lib/types"
import { type GameEvent, detectGameEvents } from "@/lib/narration"

interface UseGameNarrationResult {
  events: GameEvent[]
  latestNarration: string | null
}

export function useGameNarration(
  displayState: SpectatorState,
): UseGameNarrationResult {
  const prevStateRef = useRef<SpectatorState>(displayState)
  const lastVersionRef = useRef(displayState.state_version)
  const [latestNarration, setLatestNarration] = useState<string | null>(null)
  const eventsRef = useRef<GameEvent[]>([])

  useEffect(() => {
    const version = displayState.state_version
    if (version <= lastVersionRef.current) return

    const events = detectGameEvents(prevStateRef.current, displayState)
    prevStateRef.current = displayState
    lastVersionRef.current = version

    if (events.length > 0) {
      eventsRef.current.push(...events)
      // Use the highest-priority event for the banner
      const best = events.reduce((a, b) => (b.priority > a.priority ? b : a))
      setLatestNarration(best.narration)
    }
  }, [displayState])

  // Consume events (caller reads and clears)
  const events = eventsRef.current
  eventsRef.current = []

  return { events, latestNarration }
}
