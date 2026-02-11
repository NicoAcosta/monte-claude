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

interface ReplayOptions {
  audioEnabled?: boolean
  isSpeaking?: boolean
}

// ── Delay ranges (ms) per transition type ──

interface DelayRange { min: number; max: number }

const DELAY_RANGES: Record<string, DelayRange> = {
  dealing:        { min: 3000, max: 4500 },
  fold:           { min: 1500, max: 3000 },
  check:          { min: 1500, max: 2500 },
  call:           { min: 2000, max: 4000 },
  bet:            { min: 3000, max: 5000 },
  raise:          { min: 3500, max: 6000 },
  all_in:         { min: 4000, max: 7000 },
  community_flop: { min: 3000, max: 4500 },
  community_card: { min: 2500, max: 4000 },
  showdown:       { min: 4000, max: 6000 },
  hand_complete:  { min: 3000, max: 5000 },
  default:        { min: 1000, max: 2000 },
}

function randomDelay(key: string): number {
  const range = DELAY_RANGES[key] ?? DELAY_RANGES.default
  return range.min + Math.random() * (range.max - range.min)
}

/** Catch-up thresholds */
const CATCHUP_SOFT = 15
const CATCHUP_HARD = 30

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

  // Hand complete
  if (next.phase === "complete" && prev.phase !== "complete") {
    return { phase: "showdown", delayKey: "hand_complete" }
  }

  // Community cards changed
  if (next.community_cards.length > prev.community_cards.length) {
    const added = next.community_cards.length - prev.community_cards.length
    if (added >= 3) {
      return { phase: "community", delayKey: "community_flop" }
    }
    return { phase: "community", delayKey: "community_card" }
  }

  // Showdown
  if (
    next.phase === "showdown" &&
    prev.phase !== "showdown" &&
    prev.phase !== "complete"
  ) {
    return { phase: "showdown", delayKey: "showdown" }
  }

  // Individual actions — use action name as delay key
  if (next.recent_actions.length > 0) {
    const lastAction = next.recent_actions[next.recent_actions.length - 1]
    const action = lastAction?.action
    if (action && action in DELAY_RANGES) {
      return { phase: "action", delayKey: action }
    }
    return { phase: "action", delayKey: "default" }
  }

  return { phase: null, delayKey: "default" }
}

/**
 * Processes incoming spectator snapshots with broadcast-quality pacing.
 *
 * - Hand buffering: states only enter the replay queue once their hand is complete
 * - Randomized delays: each transition type has a min/max range
 * - Audio gate: waits for TTS to finish before advancing
 * - Catch-up: compresses delays when queue grows large
 */
export function useReplayQueue(
  consumeSnapshots: () => SpectatorState[],
  initialState: SpectatorState,
  options?: ReplayOptions,
): UseReplayQueueResult {
  const [displayState, setDisplayState] = useState<SpectatorState>(initialState)
  const [animationPhase, setAnimationPhase] = useState<AnimationPhase>(null)
  const [isReplaying, setIsReplaying] = useState(false)

  // Replay queue: states confirmed complete, ready for display
  const queueRef = useRef<SpectatorState[]>([])
  // Raw buffer: incoming states awaiting hand completion
  const rawBufferRef = useRef<SpectatorState[]>([])

  const processingRef = useRef(false)
  const displayStateRef = useRef<SpectatorState>(initialState)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const audioGatePollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Track options via ref so async callbacks always see latest values
  const optionsRef = useRef<ReplayOptions>({ audioEnabled: false, isSpeaking: false })
  useEffect(() => {
    optionsRef.current = {
      audioEnabled: options?.audioEnabled ?? false,
      isSpeaking: options?.isSpeaking ?? false,
    }
  }, [options?.audioEnabled, options?.isSpeaking])

  /**
   * Scan raw buffer and release states for completed hands into the replay queue.
   */
  const flushCompletedHands = useCallback(() => {
    const buffer = rawBufferRef.current
    if (buffer.length === 0) return

    const completedHands = new Set<number>()
    const maxHand = buffer[buffer.length - 1].hand_number

    for (const s of buffer) {
      // Explicit completion signals
      if (s.phase === "complete" || s.game_over) {
        completedHands.add(s.hand_number)
      }
      // Any hand before the latest is implicitly complete
      if (s.hand_number < maxHand) {
        completedHands.add(s.hand_number)
      }
    }

    if (completedHands.size === 0) return

    // Release all states belonging to completed hands
    let releaseUpTo = -1
    for (let i = 0; i < buffer.length; i++) {
      if (completedHands.has(buffer[i].hand_number)) {
        releaseUpTo = i
      }
    }

    if (releaseUpTo >= 0) {
      const toRelease = buffer.splice(0, releaseUpTo + 1)
      queueRef.current.push(...toRelease)
    }
  }, [])

  /**
   * Wait for TTS to finish speaking, then call advance.
   */
  const waitForAudioThenAdvance = useCallback((advance: () => void) => {
    if (!optionsRef.current.audioEnabled || !optionsRef.current.isSpeaking) {
      advance()
      return
    }

    const startTime = Date.now()
    audioGatePollRef.current = setInterval(() => {
      // Safety valve: max 15s wait
      if (Date.now() - startTime > 15000 || !optionsRef.current.isSpeaking) {
        if (audioGatePollRef.current) clearInterval(audioGatePollRef.current)
        audioGatePollRef.current = null
        // Post-audio gap: 300-800ms
        const gap = 300 + Math.random() * 500
        timeoutRef.current = setTimeout(advance, gap)
      }
    }, 100)
  }, [])

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

      // Calculate randomized delay
      let delay = randomDelay(delayKey)

      // Catch-up logic
      if (queueRef.current.length > CATCHUP_HARD) {
        delay = 200
      } else if (queueRef.current.length > CATCHUP_SOFT) {
        delay = Math.max(delay * 0.4, 300)
      }

      // After visual delay, wait for audio gate, then advance
      timeoutRef.current = setTimeout(() => {
        waitForAudioThenAdvance(step)
      }, delay)
    }

    step()
  }, [waitForAudioThenAdvance])

  // Ingest new snapshots every 200ms → raw buffer → flush completed hands
  useEffect(() => {
    const interval = setInterval(() => {
      const newSnapshots = consumeSnapshots()
      if (newSnapshots.length > 0) {
        rawBufferRef.current.push(...newSnapshots)
      }

      flushCompletedHands()

      if (queueRef.current.length > 0 && !processingRef.current) {
        processQueue()
      }
    }, 200)
    return () => clearInterval(interval)
  }, [consumeSnapshots, flushCompletedHands, processQueue])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
      if (audioGatePollRef.current) clearInterval(audioGatePollRef.current)
    }
  }, [])

  return { displayState, animationPhase, isReplaying }
}
