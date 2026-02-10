"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import type { SpectatorState } from "@/lib/types"

export type AnimationPhase =
  | "dealing"
  | "action"
  | "community"
  | "showdown"
  | null

interface UseReplayQueueResult {
  /** The state currently being shown to the viewer. */
  displayState: SpectatorState
  /** Current animation phase for child components. */
  animationPhase: AnimationPhase
  /** True if the queue has pending snapshots to replay. */
  isReplaying: boolean
}

/** Delay in ms for each type of transition. */
const DELAYS: Record<string, number> = {
  dealing: 1500,
  action_minor: 800,    // fold, check, call
  action_major: 1200,   // bet, raise, all_in
  community_flop: 2000,
  community_card: 1500, // turn, river
  showdown: 2500,
  default: 600,
}

/** Catch-up: if queue exceeds this, halve all delays. */
const CATCHUP_THRESHOLD = 15

/**
 * Determines what changed between two consecutive snapshots.
 */
function detectTransition(
  prev: SpectatorState,
  next: SpectatorState,
): { phase: AnimationPhase; delayKey: string } {
  // New hand started
  if (next.hand_number > prev.hand_number && next.phase !== prev.phase) {
    return { phase: "dealing", delayKey: "dealing" }
  }

  // Community cards changed
  if (next.community_cards.length > prev.community_cards.length) {
    const added = next.community_cards.length - prev.community_cards.length
    if (added >= 3) {
      return { phase: "community", delayKey: "community_flop" }
    }
    return { phase: "community", delayKey: "community_card" }
  }

  // Showdown / hand complete
  if (
    (next.phase === "showdown" || next.phase === "complete") &&
    prev.phase !== "showdown" &&
    prev.phase !== "complete"
  ) {
    return { phase: "showdown", delayKey: "showdown" }
  }

  // New action — check last recent_action
  if (next.recent_actions.length > 0) {
    const lastAction = next.recent_actions[next.recent_actions.length - 1]
    const action = lastAction?.action
    if (
      action === "bet" ||
      action === "raise" ||
      action === "all_in"
    ) {
      return { phase: "action", delayKey: "action_major" }
    }
    if (
      action === "fold" ||
      action === "check" ||
      action === "call"
    ) {
      return { phase: "action", delayKey: "action_minor" }
    }
  }

  return { phase: null, delayKey: "default" }
}

/**
 * Processes incoming spectator snapshots and replays them with realistic delays.
 */
export function useReplayQueue(
  consumeSnapshots: () => SpectatorState[],
  initialState: SpectatorState,
): UseReplayQueueResult {
  const [displayState, setDisplayState] = useState<SpectatorState>(initialState)
  const [animationPhase, setAnimationPhase] = useState<AnimationPhase>(null)
  const [isReplaying, setIsReplaying] = useState(false)

  const queueRef = useRef<SpectatorState[]>([])
  const processingRef = useRef(false)
  const displayStateRef = useRef<SpectatorState>(initialState)

  // Ingest new snapshots every 200ms
  useEffect(() => {
    const interval = setInterval(() => {
      const newSnapshots = consumeSnapshots()
      if (newSnapshots.length > 0) {
        queueRef.current.push(...newSnapshots)
        if (!processingRef.current) {
          processQueue()
        }
      }
    }, 200)
    return () => clearInterval(interval)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [consumeSnapshots])

  const processQueue = useCallback(() => {
    if (processingRef.current) return
    processingRef.current = true
    setIsReplaying(true)

    const step = () => {
      const next = queueRef.current.shift()
      if (!next) {
        processingRef.current = false
        setIsReplaying(false)
        setAnimationPhase(null)
        return
      }

      const prev = displayStateRef.current
      const { phase, delayKey } = detectTransition(prev, next)

      // Apply the new state
      displayStateRef.current = next
      setDisplayState(next)
      setAnimationPhase(phase)

      // Calculate delay (halve if catching up)
      let delay = DELAYS[delayKey] ?? DELAYS.default
      if (queueRef.current.length > CATCHUP_THRESHOLD) {
        delay = Math.max(delay / 2, 150)
      }

      setTimeout(step, delay)
    }

    step()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { displayState, animationPhase, isReplaying }
}
