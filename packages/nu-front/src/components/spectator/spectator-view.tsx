"use client"

import { useState, useEffect, useRef, useMemo } from "react"
import { useGameStream } from "@/hooks/use-game-stream"
import { useReplayQueue } from "@/hooks/use-replay-queue"
import { formatDuration } from "@/lib/format"
import type { SpectatorState } from "@/lib/types"
import { useGameNarration } from "@/hooks/use-game-narration"
import { useGameAudio } from "@/hooks/use-game-audio"
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
  // Game stream: polls for snapshot updates
  const { consumeSnapshots, status } = useGameStream(
    gameId,
    streamId,
    mode,
    initialState,
  )

  // Replay queue: plays back snapshots with realistic delays
  const { displayState: state, animationPhase } = useReplayQueue(
    consumeSnapshots,
    initialState,
  )

  // Dealing animation — triggered by animationPhase or hand change
  const lastHandRef = useRef(state.hand_number)
  const [dealing, setDealing] = useState(false)

  useEffect(() => {
    if (
      state.hand_number !== lastHandRef.current ||
      animationPhase === "dealing"
    ) {
      lastHandRef.current = state.hand_number
      const startTimer = setTimeout(() => setDealing(true), 0)
      const endTimer = setTimeout(() => setDealing(false), 600)
      return () => {
        clearTimeout(startTimer)
        clearTimeout(endTimer)
      }
    }
  }, [state.hand_number, animationPhase])

  // Timer
  const [timerText, setTimerText] = useState<string | null>(null)
  const [timerUrgent, setTimerUrgent] = useState(false)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (timerRef.current) clearInterval(timerRef.current)

    const deadline = state.timer?.deadline
    if (!deadline || state.current_turn == null) {
      timerRef.current = null
      return
    }

    const updateTimer = () => {
      const remaining = deadline - Date.now() / 1000
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
    timerRef.current = setInterval(updateTimer, 500)

    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
      setTimerText(null)
      setTimerUrgent(false)
    }
  }, [state.timer, state.current_turn])

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

  // Game narration & audio
  const { consumeEvents, latestNarration } = useGameNarration(state)
  useGameAudio(consumeEvents, audioEnabled)

  // Info panel toggle
  const [infoPanelOpen, setInfoPanelOpen] = useState(false)

  // Player comments — extract latest from recent_actions
  const playerComments = usePlayerComments(state)

  // Last action for overlay on player seat
  const lastAction = state.recent_actions.length > 0
    ? state.recent_actions[state.recent_actions.length - 1]
    : null

  return (
    <div
      className="flex min-h-screen flex-col bg-felt-green text-cream"
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
            animationPhase={animationPhase}
            lastAction={lastAction}
          />
        ) : (
          <WaitingScreen state={state} gameId={gameId || ""} />
        )}
      </div>

      {/* Commentary */}
      <CommentaryBanner text={state.commentary_text || latestNarration} />

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
  return useMemo(() => {
    const comments: Record<string, string> = {}
    for (const action of state.recent_actions) {
      if (action.comment) {
        comments[action.player] = action.comment
      }
    }
    return comments
  }, [state.recent_actions])
}
