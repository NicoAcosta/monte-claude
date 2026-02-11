"use client"

import { useState, useEffect, useCallback } from "react"
import {
  type SoundSettings,
  type SoundChannel,
  DEFAULT_SOUND_SETTINGS,
  STORAGE_KEY,
} from "@/lib/sound-settings"

function loadSettings(): SoundSettings {
  if (typeof window === "undefined") return DEFAULT_SOUND_SETTINGS
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT_SOUND_SETTINGS
    const parsed = JSON.parse(raw)
    // Merge with defaults so new channels added later get default values
    return {
      master: typeof parsed.master === "boolean" ? parsed.master : DEFAULT_SOUND_SETTINGS.master,
      commentator: { ...DEFAULT_SOUND_SETTINGS.commentator, ...parsed.commentator },
      playerComments: { ...DEFAULT_SOUND_SETTINGS.playerComments, ...parsed.playerComments },
      effects: { ...DEFAULT_SOUND_SETTINGS.effects, ...parsed.effects },
      ambience: { ...DEFAULT_SOUND_SETTINGS.ambience, ...parsed.ambience },
    }
  } catch {
    return DEFAULT_SOUND_SETTINGS
  }
}

export function useSoundSettings() {
  const [settings, setSettings] = useState<SoundSettings>(DEFAULT_SOUND_SETTINGS)
  const [hydrated, setHydrated] = useState(false)

  // Load from localStorage on mount (client-only)
  useEffect(() => {
    setSettings(loadSettings())
    setHydrated(true)
  }, [])

  // Persist on every change (skip initial hydration write)
  useEffect(() => {
    if (!hydrated) return
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
    } catch {
      // localStorage full or unavailable — ignore
    }
  }, [settings, hydrated])

  const toggleMaster = useCallback(() => {
    setSettings((s) => ({ ...s, master: !s.master }))
  }, [])

  const toggleChannel = useCallback((channel: SoundChannel) => {
    setSettings((s) => ({
      ...s,
      [channel]: { ...s[channel], enabled: !s[channel].enabled },
    }))
  }, [])

  const setChannelVolume = useCallback((channel: SoundChannel, volume: number) => {
    setSettings((s) => ({
      ...s,
      [channel]: { ...s[channel], volume: Math.max(0, Math.min(1, volume)) },
    }))
  }, [])

  return { settings, toggleMaster, toggleChannel, setChannelVolume }
}
