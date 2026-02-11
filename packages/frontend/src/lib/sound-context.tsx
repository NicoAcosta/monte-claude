"use client"

import { createContext, useContext, useEffect, useRef } from "react"
import { useSoundSettings } from "@/hooks/use-sound-settings"
import { CasinoAmbience } from "@/lib/casino-ambience"
import type { SoundSettings, SoundChannel } from "@/lib/sound-settings"

interface SoundContextValue {
  settings: SoundSettings
  toggleMaster: () => void
  toggleChannel: (channel: SoundChannel) => void
  setChannelVolume: (channel: SoundChannel, volume: number) => void
  /** Shared AudioContext — created on first master enable (user gesture). */
  getAudioCtx: () => AudioContext | null
  /** Shared effects GainNode for spectator sound effects. */
  getEffectsGain: () => GainNode | null
}

const SoundCtx = createContext<SoundContextValue | null>(null)

export function useSoundContext(): SoundContextValue {
  const ctx = useContext(SoundCtx)
  if (!ctx) throw new Error("useSoundContext must be used within <SoundProvider>")
  return ctx
}

export function SoundProvider({ children }: { children: React.ReactNode }) {
  const { settings, toggleMaster, toggleChannel, setChannelVolume } = useSoundSettings()

  const audioCtxRef = useRef<AudioContext | null>(null)
  const effectsGainRef = useRef<GainNode | null>(null)
  const ambienceGainRef = useRef<GainNode | null>(null)
  const ambienceRef = useRef<CasinoAmbience | null>(null)

  // Lazily create the AudioContext + gain nodes (must be from user gesture)
  function ensureAudioCtx(): AudioContext | null {
    if (typeof window === "undefined") return null
    if (audioCtxRef.current) return audioCtxRef.current

    try {
      const ctx = new (
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
      )()
      audioCtxRef.current = ctx

      const effectsGain = ctx.createGain()
      effectsGain.gain.value = settings.effects.enabled ? settings.effects.volume : 0
      effectsGain.connect(ctx.destination)
      effectsGainRef.current = effectsGain

      const ambienceGain = ctx.createGain()
      ambienceGain.gain.value = settings.ambience.enabled ? settings.ambience.volume : 0
      ambienceGain.connect(ctx.destination)
      ambienceGainRef.current = ambienceGain

      ambienceRef.current = new CasinoAmbience(ctx, ambienceGain)
      return ctx
    } catch {
      return null
    }
  }

  // ── Init audio on first master enable ──
  useEffect(() => {
    if (!settings.master) return
    const ctx = ensureAudioCtx()
    if (!ctx) return

    if (settings.ambience.enabled && ambienceRef.current && !ambienceRef.current.isRunning()) {
      ambienceRef.current.start()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings.master])

  // ── Sync gain node volumes ──
  useEffect(() => {
    if (effectsGainRef.current) {
      effectsGainRef.current.gain.value =
        settings.master && settings.effects.enabled ? settings.effects.volume : 0
    }
    if (ambienceGainRef.current) {
      ambienceGainRef.current.gain.value =
        settings.master && settings.ambience.enabled ? settings.ambience.volume : 0
    }
  }, [
    settings.master,
    settings.effects.enabled,
    settings.effects.volume,
    settings.ambience.enabled,
    settings.ambience.volume,
  ])

  // ── Ambience start/stop ──
  useEffect(() => {
    const wantAmbience = settings.master && settings.ambience.enabled
    const ambience = ambienceRef.current

    if (wantAmbience && ambience && !ambience.isRunning()) {
      ambience.start()
    } else if (!wantAmbience && ambience?.isRunning()) {
      ambience.stop()
    }
  }, [settings.master, settings.ambience.enabled])

  // ── Master off: stop ambience ──
  useEffect(() => {
    if (!settings.master) {
      ambienceRef.current?.stop()
    }
  }, [settings.master])

  const value: SoundContextValue = {
    settings,
    toggleMaster,
    toggleChannel,
    setChannelVolume,
    getAudioCtx: () => audioCtxRef.current,
    getEffectsGain: () => effectsGainRef.current,
  }

  return <SoundCtx value={value}>{children}</SoundCtx>
}
