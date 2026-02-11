"use client"

import { useState, useEffect, useRef, useCallback } from "react"

export type ConnectionStatus = "connecting" | "connected" | "disconnected"

interface UsePollResult<T> {
  data: T | null
  error: Error | null
  status: ConnectionStatus
}

export function usePoll<T>(
  url: string,
  intervalMs: number,
  options?: { enabled?: boolean }
): UsePollResult<T> {
  const enabled = options?.enabled ?? true
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [status, setStatus] = useState<ConnectionStatus>("connecting")
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const abortRef = useRef<AbortController | null>(null)

  const poll = useCallback(async () => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const res = await fetch(url, { signal: controller.signal })
      if (!res.ok) throw new Error(`${res.status}`)
      const json = await res.json()
      setData(json)
      setError(null)
      setStatus("connected")
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return
      setError(err instanceof Error ? err : new Error(String(err)))
      setStatus("disconnected")
    }
  }, [url])

  useEffect(() => {
    if (!enabled) return

    poll()
    intervalRef.current = setInterval(poll, intervalMs)

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
      abortRef.current?.abort()
    }
  }, [poll, intervalMs, enabled])

  return { data, error, status }
}
