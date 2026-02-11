"use client"

import { useState, useEffect, useRef, useMemo } from "react"
import { useGameStream } from "@/hooks/use-game-stream"
import { useReplayQueue } from "@/hooks/use-replay-queue"
import { formatDuration, formatChips } from "@/lib/format"
import type { SpectatorState } from "@/lib/types"
import { useGameNarration } from "@/hooks/use-game-narration"
import { useGameAudio } from "@/hooks/use-game-audio"
import { useSoundContext } from "@/lib/sound-context"
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
  // Sound settings from shared context (persisted to localStorage)
  const { settings, toggleMaster, toggleChannel, setChannelVolume, getAudioCtx, getEffectsGain } = useSoundContext()
  // isSpeaking synced from useGameAudio below — one-render lag is fine
  // because useReplayQueue reads it from a ref in async callbacks
  const [isSpeaking, setIsSpeaking] = useState(false)

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
    { audioEnabled: settings.master, isSpeaking },
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
      const endTimer = setTimeout(() => setDealing(false), 1500)
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

  // Game narration & audio
  const { consumeEvents, latestNarration } = useGameNarration(state)
  const { isSpeaking: audioIsSpeaking } = useGameAudio(consumeEvents, settings, getAudioCtx, getEffectsGain)
  useEffect(() => { setIsSpeaking(audioIsSpeaking) }, [audioIsSpeaking])

  // Between-hands summary
  const prevDisplayRef = useRef<SpectatorState>(state)
  const [handSummary, setHandSummary] = useState<{
    winner: string
    pot: number
    handNumber: number
  } | null>(null)

  useEffect(() => {
    if (state.phase === "complete" && state.hand_number > 0) {
      const prev = prevDisplayRef.current
      for (const np of state.players) {
        const pp = prev.players.find((p) => p.id === np.id)
        if (pp && np.chips > pp.chips && prev.pot > 0) {
          setHandSummary({
            winner: np.name,
            pot: prev.pot,
            handNumber: state.hand_number,
          })
          break
        }
      }
    } else {
      setHandSummary(null)
    }
    prevDisplayRef.current = state
  }, [state])

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
        settings={settings}
        onToggleMaster={toggleMaster}
        onToggleChannel={toggleChannel}
        onSetVolume={setChannelVolume}
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
      <div className="relative flex flex-1 items-center justify-center p-5">
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

        {/* Between-hands summary overlay */}
        {handSummary && (
          <div
            className="absolute left-1/2 top-[15%] z-10 -translate-x-1/2 rounded-xl border border-dealer-gold/30 bg-black/70 px-8 py-4 text-center backdrop-blur-sm"
            style={{ animation: "fade-slide-in 0.5s ease" }}
          >
            <div className="text-[10px] uppercase tracking-[2px] text-sage">
              Hand #{handSummary.handNumber} Complete
            </div>
            <div className="mt-1 text-lg font-bold text-dealer-gold">
              {handSummary.winner} wins {formatChips(handSummary.pot)}
            </div>
          </div>
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
