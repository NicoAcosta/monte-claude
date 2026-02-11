"use client"

import { useEffect, useRef, type ReactNode } from "react"
import type { SoundSettings, SoundChannel } from "@/lib/sound-settings"
import { CHANNELS, CHANNEL_META } from "@/lib/sound-settings"
import { MicIcon, ChatBubbleIcon, ChipSoundIcon, EqualizerIcon } from "@/components/icons"

const CHANNEL_ICONS: Record<SoundChannel, ReactNode> = {
  commentator: <MicIcon className="h-3.5 w-3.5" />,
  playerComments: <ChatBubbleIcon className="h-3.5 w-3.5" />,
  effects: <ChipSoundIcon className="h-3.5 w-3.5" />,
  ambience: <EqualizerIcon className="h-3.5 w-3.5" />,
}

interface SoundMixerProps {
  settings: SoundSettings
  onToggleChannel: (channel: SoundChannel) => void
  onSetVolume: (channel: SoundChannel, volume: number) => void
  open: boolean
  onClose: () => void
}

export function SoundMixer({
  settings,
  onToggleChannel,
  onSetVolume,
  open,
  onClose,
}: SoundMixerProps) {
  const panelRef = useRef<HTMLDivElement>(null)

  // Close on Escape
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    document.addEventListener("keydown", handler)
    return () => document.removeEventListener("keydown", handler)
  }, [open, onClose])

  // Close on click outside
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        onClose()
      }
    }
    // Delay to avoid catching the click that opened the mixer
    const timer = setTimeout(() => {
      document.addEventListener("mousedown", handler)
    }, 0)
    return () => {
      clearTimeout(timer)
      document.removeEventListener("mousedown", handler)
    }
  }, [open, onClose])

  return (
    <div
      ref={panelRef}
      className={`sound-mixer ${open ? "open" : ""} absolute right-0 top-full z-20 mt-2 w-[280px] rounded-lg border border-white/[0.08] bg-black/85 shadow-xl shadow-black/40 backdrop-blur-md`}
      role="dialog"
      aria-label="Sound mixer"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-2.5">
        <span className="text-[10px] font-semibold uppercase tracking-[1.5px] text-gold-muted">
          Sound Mixer
        </span>
        <button
          onClick={onClose}
          className="flex h-5 w-5 items-center justify-center rounded text-sage transition-colors hover:text-white"
          aria-label="Close sound mixer"
        >
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
            <path d="M1 1l8 8M9 1l-8 8" />
          </svg>
        </button>
      </div>

      {/* Channels */}
      <div className="flex flex-col gap-0.5 px-4 py-3">
        {CHANNELS.map((channel) => {
          const meta = CHANNEL_META[channel]
          const ch = settings[channel]
          const isActive = settings.master && ch.enabled
          const pct = Math.round(ch.volume * 100)

          return (
            <ChannelRow
              key={channel}
              icon={CHANNEL_ICONS[channel]}
              label={meta.label}
              enabled={ch.enabled}
              active={isActive}
              volume={ch.volume}
              onToggle={() => onToggleChannel(channel)}
              onVolumeChange={(v) => onSetVolume(channel, v)}
            />
          )
        })}
      </div>
    </div>
  )
}

function ChannelRow({
  icon,
  label,
  enabled,
  active,
  volume,
  onToggle,
  onVolumeChange,
}: {
  icon: ReactNode
  label: string
  enabled: boolean
  active: boolean
  volume: number
  onToggle: () => void
  onVolumeChange: (v: number) => void
}) {
  const pct = Math.round(volume * 100)

  // Compute slider track gradient
  const trackBg = active
    ? `linear-gradient(to right, var(--color-dealer-gold) 0%, var(--color-dealer-gold) ${pct}%, rgba(255,255,255,0.1) ${pct}%, rgba(255,255,255,0.1) 100%)`
    : "rgba(255,255,255,0.06)"

  return (
    <div className="flex items-center gap-3 py-1.5">
      {/* Icon */}
      <span
        className={`flex w-5 items-center justify-center ${active ? "text-dealer-gold" : "text-sage/30"}`}
        aria-hidden
      >
        {icon}
      </span>

      {/* Label + slider */}
      <div className="flex flex-1 flex-col gap-1">
        <span className={`text-[11px] font-medium ${active ? "text-felt-text" : "text-sage/50"}`}>
          {label}
        </span>
        <input
          type="range"
          min={0}
          max={100}
          value={pct}
          onChange={(e) => onVolumeChange(Number(e.target.value) / 100)}
          className="sound-slider"
          disabled={!enabled}
          style={{ background: trackBg }}
          aria-label={`${label} volume`}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={pct}
        />
      </div>

      {/* Toggle switch */}
      <button
        onClick={onToggle}
        className={`toggle-switch ${enabled ? "on" : ""}`}
        role="switch"
        aria-checked={enabled}
        aria-label={`Toggle ${label}`}
      >
        <span className="toggle-switch-thumb" />
      </button>
    </div>
  )
}
