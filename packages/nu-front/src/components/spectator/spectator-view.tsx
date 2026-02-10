"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import { usePoll } from "@/hooks/use-poll"
import { formatDuration } from "@/lib/format"
import type { SpectatorState } from "@/lib/types"
import { HeaderBar } from "./header-bar"
import { InfoPanel } from "./info-panel"
import { WaitingScreen } from "./waiting-screen"
import { PokerTable } from "./poker-table"
import { ActionLog } from "./action-log"
import { CommentaryBanner } from "./commentary-banner"
import { WinnerOverlay } from "./winner-overlay"

interface SpectatorViewProps {
  initialState: SpectatorState
  gameId?: string
  streamId?: string
  mode: "game" | "stream"
}

export function SpectatorView({
  initialState,
  gameId,
  streamId,
  mode,
}: SpectatorViewProps) {
  const pollUrl =
    mode === "stream"
      ? `/stream/${streamId}/data`
      : `/game/${gameId}/spectator`

  const { data, status } = usePoll<SpectatorState>(pollUrl, 2000)
  const state = data ?? initialState

  // Track hand number for dealing animation
  const lastHandRef = useRef(state.hand_number)
  const [dealing, setDealing] = useState(false)

  useEffect(() => {
    if (state.hand_number !== lastHandRef.current) {
      lastHandRef.current = state.hand_number
      setDealing(true)
      const timer = setTimeout(() => setDealing(false), 600)
      return () => clearTimeout(timer)
    }
  }, [state.hand_number])

  // Timer
  const [timerText, setTimerText] = useState<string | null>(null)
  const [timerUrgent, setTimerUrgent] = useState(false)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (timerRef.current) clearInterval(timerRef.current)

    if (!state.timer?.deadline || state.current_turn == null) {
      setTimerText(null)
      setTimerUrgent(false)
      return
    }

    const updateTimer = () => {
      const remaining = state.timer!.deadline - Date.now() / 1000
      if (remaining <= 0) {
        setTimerText("0:00")
        setTimerUrgent(true)
        return
      }
      const m = Math.floor(remaining / 60)
      const s = Math.floor(remaining % 60)
      setTimerText(`${m}:${s.toString().padStart(2, "0")}`)
      setTimerUrgent(remaining < 10)
    }

    updateTimer()
    timerRef.current = setInterval(updateTimer, 100)

    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [state.timer?.deadline, state.current_turn])

  // Game duration
  const [gameDuration, setGameDuration] = useState("")
  useEffect(() => {
    if (!state.game_started_at) return
    const update = () => {
      const elapsed = Date.now() / 1000 - state.game_started_at!
      setGameDuration(formatDuration(elapsed))
    }
    update()
    const interval = setInterval(update, 1000)
    return () => clearInterval(interval)
  }, [state.game_started_at])

  // Stream duration
  const [streamDuration, setStreamDuration] = useState<string | null>(null)
  useEffect(() => {
    if (!state.stream_created_at) return
    const update = () => {
      const elapsed = Date.now() / 1000 - state.stream_created_at!
      setStreamDuration(formatDuration(elapsed))
    }
    update()
    const interval = setInterval(update, 1000)
    return () => clearInterval(interval)
  }, [state.stream_created_at])

  // Audio toggle
  const [audioEnabled, setAudioEnabled] = useState(false)

  // Info panel toggle
  const [infoPanelOpen, setInfoPanelOpen] = useState(false)

  // Player comments — extract latest from recent_actions and chat_log
  const playerComments = usePlayerComments(state)

  return (
    <div
      className="flex min-h-screen flex-col"
      style={{ background: "#0f2d1a", color: "#e8e0d0" }}
    >
      <HeaderBar
        handNumber={state.hand_number}
        phase={state.phase}
        gameDuration={gameDuration}
        connectionStatus={status}
        audioEnabled={audioEnabled}
        onAudioToggle={() => setAudioEnabled((v) => !v)}
        infoPanelOpen={infoPanelOpen}
        onInfoToggle={() => setInfoPanelOpen((v) => !v)}
      />

      <InfoPanel
        state={state}
        visible={infoPanelOpen}
        gameDuration={gameDuration}
        streamDuration={streamDuration}
      />

      {/* Table area */}
      <div className="flex flex-1 items-center justify-center p-5">
        {state.started ? (
          <PokerTable
            state={state}
            dealing={dealing}
            timerText={timerText}
            timerUrgent={timerUrgent}
            playerComments={playerComments}
          />
        ) : (
          <WaitingScreen state={state} gameId={gameId || ""} />
        )}
      </div>

      {/* Commentary */}
      {state.commentary_text && (
        <CommentaryBanner
          text={state.commentary_text}
          audioEnabled={audioEnabled}
        />
      )}

      {/* Action log */}
      <ActionLog actions={state.recent_actions} />

      {/* Winner overlay */}
      {state.game_over && state.winner && (
        <WinnerOverlay winner={state.winner} />
      )}
    </div>
  )
}

function usePlayerComments(state: SpectatorState): Record<string, string> {
  const commentsRef = useRef<Record<string, string>>({})

  // Extract latest comment per player from recent_actions
  const comments: Record<string, string> = {}
  for (const action of state.recent_actions) {
    if (action.comment) {
      comments[action.player] = action.comment
    }
  }

  // Only update ref if comments changed to avoid unnecessary rerenders
  const key = JSON.stringify(comments)
  const prevKey = useRef("")
  if (key !== prevKey.current) {
    prevKey.current = key
    commentsRef.current = comments
  }

  return commentsRef.current
}
