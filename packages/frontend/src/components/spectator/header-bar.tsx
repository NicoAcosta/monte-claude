"use client"

import Link from "next/link"
import { ConnectionStatus } from "@/components/connection-status"
import type { ConnectionStatus as ConnStatus } from "@/hooks/use-poll"

interface HeaderBarProps {
  handNumber: number
  phase: string
  gameDuration: string
  connectionStatus: ConnStatus
  audioEnabled: boolean
  onAudioToggle: () => void
  infoPanelOpen: boolean
  onInfoToggle: () => void
}

const PHASE_COLORS: Record<string, string> = {
  "pre-flop": "bg-table-green text-dealer-gold",
  flop: "bg-table-green text-dealer-gold",
  turn: "bg-table-green text-dealer-gold",
  river: "bg-table-green text-dealer-gold",
  showdown: "bg-dealer-gold/20 text-dealer-gold",
  waiting: "bg-white/10 text-white/50",
}

export function HeaderBar({
  handNumber,
  phase,
  gameDuration,
  connectionStatus,
  audioEnabled,
  onAudioToggle,
  infoPanelOpen,
  onInfoToggle,
}: HeaderBarProps) {
  return (
    <header className="flex flex-shrink-0 items-center justify-between border-b border-white/[0.06] bg-black/30 px-6 py-3">
      <div className="flex items-center gap-3">
        <Link
          href="/games"
          className="text-[13px] text-sage no-underline hover:text-white"
        >
          &larr; Games
        </Link>
        <h1 className="text-sm font-semibold uppercase tracking-[1.5px] text-dealer-gold">
          Spectator
        </h1>
      </div>

      <div className="flex items-center gap-5 text-[13px] text-sage">
        {handNumber > 0 && <span>Hand #{handNumber}</span>}
        {phase && (
          <span
            className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider ${PHASE_COLORS[phase] || PHASE_COLORS.waiting}`}
          >
            {phase}
          </span>
        )}
        {gameDuration && (
          <span className="tabular-nums" title="Game duration">
            &#9201; {gameDuration}
          </span>
        )}
        <ConnectionStatus status={connectionStatus} />
        <button
          onClick={onInfoToggle}
          className={`flex h-7 w-7 items-center justify-center rounded-full border text-sm font-bold italic transition-colors ${
            infoPanelOpen
              ? "border-dealer-gold text-dealer-gold"
              : "border-white/15 text-sage hover:border-dealer-gold hover:text-dealer-gold"
          }`}
          style={{ fontFamily: "Georgia, serif" }}
          title="Game info"
        >
          i
        </button>
        <button
          onClick={onAudioToggle}
          className={`rounded-md border px-2.5 py-1 text-[13px] transition-colors ${
            audioEnabled
              ? "border-dealer-gold text-dealer-gold"
              : "border-white/15 text-sage hover:border-dealer-gold hover:text-dealer-gold"
          }`}
          title="Toggle audio commentary"
        >
          Sound: {audioEnabled ? "ON" : "OFF"}
        </button>
      </div>
    </header>
  )
}
