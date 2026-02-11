"use client"

import { useState } from "react"
import Link from "next/link"
import { ConnectionStatus } from "@/components/connection-status"
import type { ConnectionStatus as ConnStatus } from "@/hooks/use-poll"
import type { SoundSettings, SoundChannel } from "@/lib/sound-settings"
import { SpeakerOnIcon, SpeakerOffIcon, EqualizerIcon } from "@/components/icons"
import { SoundMixer } from "./sound-mixer"

interface HeaderBarProps {
  handNumber: number
  phase: string
  gameDuration: string
  connectionStatus: ConnStatus
  settings: SoundSettings
  onToggleMaster: () => void
  onToggleChannel: (channel: SoundChannel) => void
  onSetVolume: (channel: SoundChannel, volume: number) => void
  infoPanelOpen: boolean
  onInfoToggle: () => void
}

const PHASE_COLORS: Record<string, string> = {
  preflop: "bg-table-green/80 text-felt-text",
  flop: "bg-sb-blue/25 text-sb-blue",
  turn: "bg-dealer-gold/20 text-dealer-gold",
  river: "bg-danger/20 text-danger",
  showdown: "bg-dealer-gold/30 text-dealer-gold",
  complete: "bg-white/10 text-sage",
  waiting: "bg-white/10 text-white/50",
}

export function HeaderBar({
  handNumber,
  phase,
  gameDuration,
  connectionStatus,
  settings,
  onToggleMaster,
  onToggleChannel,
  onSetVolume,
  infoPanelOpen,
  onInfoToggle,
}: HeaderBarProps) {
  const [mixerOpen, setMixerOpen] = useState(false)

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

        {/* Sound controls */}
        <div className="relative flex items-center gap-1.5">
          {/* Master toggle */}
          <button
            onClick={onToggleMaster}
            className={`flex h-7 w-7 items-center justify-center rounded-full border transition-colors ${
              settings.master
                ? "border-dealer-gold text-dealer-gold"
                : "border-white/15 text-sage hover:border-dealer-gold hover:text-dealer-gold"
            }`}
            title={settings.master ? "Mute all sound" : "Enable sound"}
            aria-label="Toggle all sound"
          >
            {settings.master ? (
              <SpeakerOnIcon className="h-3.5 w-3.5" />
            ) : (
              <SpeakerOffIcon className="h-3.5 w-3.5" />
            )}
          </button>

          {/* Mixer toggle */}
          <button
            onClick={() => setMixerOpen((v) => !v)}
            className={`flex h-7 w-7 items-center justify-center rounded-full border transition-colors ${
              mixerOpen
                ? "border-dealer-gold text-dealer-gold"
                : "border-white/15 text-sage hover:border-dealer-gold hover:text-dealer-gold"
            }`}
            title="Sound mixer"
            aria-label="Open sound mixer"
            aria-expanded={mixerOpen}
            aria-haspopup="dialog"
          >
            <EqualizerIcon className="h-3 w-3" />
          </button>

          {/* Mixer popover */}
          <SoundMixer
            settings={settings}
            onToggleChannel={onToggleChannel}
            onSetVolume={onSetVolume}
            open={mixerOpen}
            onClose={() => setMixerOpen(false)}
          />
        </div>
      </div>
    </header>
  )
}
