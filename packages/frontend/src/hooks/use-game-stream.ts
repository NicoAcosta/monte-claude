"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import type { SpectatorState } from "@/lib/types"
import { usePoll, type ConnectionStatus } from "./use-poll"

interface UseGameStreamResult {
  /** Consume new snapshots (clears them from the internal queue). */
  consumeSnapshots: () => SpectatorState[]
  /** Connection status. */
  status: ConnectionStatus
  /** Latest raw state (for initial render before replay starts). */
  latestState: SpectatorState | null
}

/**
 * Connects to the spectator WebSocket for real-time game state updates.
 * Falls back to HTTP polling if WebSocket is unavailable or disconnects.
 * Streams always use HTTP polling (no WebSocket endpoint for streams).
 */
export function useGameStream(
  gameId: string | undefined,
  streamId: string | undefined,
  mode: "game" | "stream",
  initialState: SpectatorState,
): UseGameStreamResult {
  const [status, setStatus] = useState<ConnectionStatus>("connecting")
  const [latestState, setLatestState] = useState<SpectatorState | null>(initialState)
  const queueRef = useRef<SpectatorState[]>([])
  const wsRef = useRef<WebSocket | null>(null)
  const [usePolling, setUsePolling] = useState(mode === "stream")
  // SpectatorResponse omits state_version — init to 0, inject from WS envelope
  const lastVersionRef = useRef(0)
  const lastFingerprintRef = useRef("")

  // WebSocket connection (game mode only — streams don't have WS endpoints)
  useEffect(() => {
    if (mode === "stream" || !gameId) return

    const wsBase = process.env.NEXT_PUBLIC_GAME_WS_URL || "ws://localhost:8001"
    const ws = new WebSocket(`${wsBase}/ws/game/${gameId}/spectator`)
    wsRef.current = ws

    ws.onopen = () => setStatus("connected")

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        if (msg.type === "state" && msg.data) {
          const state = msg.data as SpectatorState
          // state_version lives in the WS envelope, NOT inside SpectatorResponse
          const version = msg.state_version ?? state.state_version ?? 0
          if (version > lastVersionRef.current) {
            lastVersionRef.current = version
            state.state_version = version
            queueRef.current.push(state)
            setLatestState(state)
          }
        }
        // "ping" messages are heartbeats — no action needed
      } catch {
        // Ignore malformed messages
      }
    }

    ws.onerror = () => {
      setUsePolling(true)
    }

    ws.onclose = () => {
      setStatus("disconnected")
      setUsePolling(true)
    }

    return () => {
      ws.close()
      wsRef.current = null
    }
  }, [gameId, mode])

  // HTTP polling fallback (streams always, games only if WS fails)
  const fallbackUrl =
    mode === "stream"
      ? `/api/streams/${streamId}/data`
      : `/api/games/${gameId}/spectator`

  const { data: fallbackData, status: fallbackStatus } = usePoll<SpectatorState>(
    fallbackUrl,
    2000,
    { enabled: usePolling },
  )

  // Push fallback poll results into queue.
  // HTTP SpectatorResponse has no state_version — dedupe via composite fingerprint.
  useEffect(() => {
    if (!usePolling || !fallbackData) return
    const fp = `${fallbackData.hand_number}:${fallbackData.phase}:${fallbackData.recent_actions.length}:${fallbackData.pot}:${fallbackData.community_cards.length}:${fallbackData.game_over}`
    if (fp !== lastFingerprintRef.current) {
      lastFingerprintRef.current = fp
      lastVersionRef.current += 1
      fallbackData.state_version = lastVersionRef.current
      queueRef.current.push(fallbackData)
      setLatestState(fallbackData)
    }
  }, [fallbackData, usePolling])

  const consumeSnapshots = useCallback(() => {
    const items = queueRef.current
    queueRef.current = []
    return items
  }, [])

  return {
    consumeSnapshots,
    status: usePolling ? fallbackStatus : status,
    latestState,
  }
}
