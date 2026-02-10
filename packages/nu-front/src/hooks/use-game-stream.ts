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
 * Polls the snapshots endpoint for incremental spectator state updates.
 * Falls back to regular polling if snapshots are unavailable.
 */
export function useGameStream(
  gameId: string | undefined,
  streamId: string | undefined,
  mode: "game" | "stream",
  initialState: SpectatorState,
): UseGameStreamResult {
  const snapshotUrl =
    mode === "stream"
      ? `/stream/${streamId}/snapshots`
      : `/game/${gameId}/spectator/snapshots`

  const [status, setStatus] = useState<ConnectionStatus>("connecting")
  const [latestState, setLatestState] = useState<SpectatorState | null>(initialState)
  const lastSeqRef = useRef(initialState.state_version ?? 0)
  const queueRef = useRef<SpectatorState[]>([])
  const [useFallback, setUseFallback] = useState(false)

  // Regular polling fallback URL
  const fallbackUrl =
    mode === "stream"
      ? `/stream/${streamId}/data`
      : `/game/${gameId}/spectator`

  // Snapshot polling
  const pollSnapshots = useCallback(async () => {
    if (useFallback) return

    try {
      const res = await fetch(`${snapshotUrl}?after=${lastSeqRef.current}`)
      if (!res.ok) {
        if (res.status === 404) {
          // Snapshots not available — fall back to regular polling
          setUseFallback(true)
          return
        }
        throw new Error(`${res.status}`)
      }
      const snapshots: SpectatorState[] = await res.json()
      if (snapshots.length > 0) {
        queueRef.current.push(...snapshots)
        const last = snapshots[snapshots.length - 1]
        lastSeqRef.current = last.state_version ?? lastSeqRef.current
        setLatestState(last)
      }
      setStatus("connected")
    } catch {
      setStatus("disconnected")
    }
  }, [snapshotUrl, useFallback])

  useEffect(() => {
    if (useFallback) return

    pollSnapshots()
    const interval = setInterval(pollSnapshots, 500)
    return () => clearInterval(interval)
  }, [pollSnapshots, useFallback])

  // Fallback: regular polling at 2s
  const { data: fallbackData, status: fallbackStatus } = usePoll<SpectatorState>(
    fallbackUrl,
    2000,
    { enabled: useFallback },
  )

  // When in fallback mode, push each new poll result as a "snapshot"
  const lastFallbackVersionRef = useRef(0)
  useEffect(() => {
    if (!useFallback || !fallbackData) return
    const version = fallbackData.state_version ?? 0
    if (version > lastFallbackVersionRef.current) {
      lastFallbackVersionRef.current = version
      queueRef.current.push(fallbackData)
      setLatestState(fallbackData)
    }
  }, [fallbackData, useFallback])

  const consumeSnapshots = useCallback(() => {
    const items = queueRef.current
    queueRef.current = []
    return items
  }, [])

  return {
    consumeSnapshots,
    status: useFallback ? fallbackStatus : status,
    latestState,
  }
}
