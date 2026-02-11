"use client"

import { useEffect, useRef, useState } from "react"
import type { GameEvent } from "@/lib/narration"
import type { SoundSettings } from "@/lib/sound-settings"

const SPEECH_RATE = 1.1
const MAX_QUEUE = 3

/**
 * Handles narration speech + sound effects for the spectator view.
 * Ambience is managed by the SoundProvider context, not here.
 *
 * @param getAudioCtx  — returns the shared AudioContext from SoundProvider
 * @param getEffectsGain — returns the shared effects GainNode from SoundProvider
 */
export function useGameAudio(
  consumeEvents: () => GameEvent[],
  settings: SoundSettings,
  getAudioCtx: () => AudioContext | null,
  getEffectsGain: () => GainNode | null,
): { isSpeaking: boolean } {
  const queueRef = useRef<GameEvent[]>([])
  const speakingRef = useRef(false)
  const settingsRef = useRef(settings)
  const [isSpeaking, setIsSpeaking] = useState(false)

  // Keep settings ref in sync for callbacks
  useEffect(() => {
    settingsRef.current = settings
  }, [settings])

  // ── Cancel speech when master or speech channels turn off ──
  useEffect(() => {
    if (!settings.master || (!settings.commentator.enabled && !settings.playerComments.enabled)) {
      window.speechSynthesis?.cancel()
      queueRef.current = []
      speakingRef.current = false
      setIsSpeaking(false)
    }
    return () => {
      window.speechSynthesis?.cancel()
      queueRef.current = []
    }
  }, [settings.master, settings.commentator.enabled, settings.playerComments.enabled])

  // ── Poll for new events every 200ms ──
  useEffect(() => {
    if (!settings.master) return

    const interval = setInterval(() => {
      const events = consumeEvents()
      if (events.length === 0) return

      const s = settingsRef.current
      const ctx = getAudioCtx()
      const effectsGain = getEffectsGain()

      for (const ev of events) {
        // Sound effects — route through shared effects gain
        if (ev.soundEffect && s.effects.enabled && ctx && effectsGain) {
          playSound(ev.soundEffect, ctx, effectsGain)
        }

        // Speech — filter by channel
        if (
          (ev.channel === "commentator" && s.commentator.enabled) ||
          (ev.channel === "playerComment" && s.playerComments.enabled)
        ) {
          queueRef.current.push(ev)
        }
      }

      // Trim queue by priority
      if (queueRef.current.length > MAX_QUEUE) {
        queueRef.current.sort((a, b) => b.priority - a.priority)
        queueRef.current = queueRef.current.slice(0, MAX_QUEUE)
      }

      if (!speakingRef.current) {
        speakNext(queueRef, speakingRef, settingsRef, setIsSpeaking)
      }
    }, 200)

    return () => clearInterval(interval)
  }, [consumeEvents, settings.master, getAudioCtx, getEffectsGain])

  return { isSpeaking }
}

// ── Speech ──

function speakNext(
  queueRef: React.MutableRefObject<GameEvent[]>,
  speakingRef: React.MutableRefObject<boolean>,
  settingsRef: React.MutableRefObject<SoundSettings>,
  onSpeakingChange: (v: boolean) => void,
) {
  const s = settingsRef.current
  if (!s.master) {
    speakingRef.current = false
    onSpeakingChange(false)
    return
  }

  const next = queueRef.current.shift()
  if (!next) {
    speakingRef.current = false
    onSpeakingChange(false)
    return
  }

  if (typeof window === "undefined" || !window.speechSynthesis) {
    speakingRef.current = false
    onSpeakingChange(false)
    return
  }

  // Per-channel volume and pitch
  const isPlayer = next.channel === "playerComment"
  const volume = isPlayer ? s.playerComments.volume : s.commentator.volume

  speakingRef.current = true
  onSpeakingChange(true)
  const utterance = new SpeechSynthesisUtterance(next.narration)
  utterance.rate = SPEECH_RATE
  utterance.pitch = isPlayer ? 1.15 : 1
  utterance.volume = volume
  utterance.onend = () => speakNext(queueRef, speakingRef, settingsRef, onSpeakingChange)
  utterance.onerror = () => speakNext(queueRef, speakingRef, settingsRef, onSpeakingChange)
  window.speechSynthesis.speak(utterance)
}

// ── Sound effects ──

function playSound(
  type: "deal" | "chip" | "allin" | "fold" | "check",
  ctx: AudioContext,
  dest: GainNode,
) {
  switch (type) {
    case "chip":
      playChipSound(ctx, dest)
      break
    case "deal":
      playDealSound(ctx, dest)
      break
    case "allin":
      playAllInSound(ctx, dest)
      break
    case "fold":
      playFoldSound(ctx, dest)
      break
    case "check":
      playCheckSound(ctx, dest)
      break
  }
}

function playChipSound(ctx: AudioContext, dest: GainNode) {
  const duration = 0.05
  const buffer = ctx.createBuffer(1, ctx.sampleRate * duration, ctx.sampleRate)
  const data = buffer.getChannelData(0)
  for (let i = 0; i < data.length; i++) {
    data[i] = (Math.random() * 2 - 1) * Math.exp(-i / (ctx.sampleRate * 0.01))
  }
  const source = ctx.createBufferSource()
  source.buffer = buffer
  const gain = ctx.createGain()
  gain.gain.value = 0.15
  source.connect(gain).connect(dest)
  source.start()
}

function playDealSound(ctx: AudioContext, dest: GainNode) {
  const duration = 0.15
  const buffer = ctx.createBuffer(1, ctx.sampleRate * duration, ctx.sampleRate)
  const data = buffer.getChannelData(0)
  for (let i = 0; i < data.length; i++) {
    data[i] = (Math.random() * 2 - 1) * Math.exp(-i / (ctx.sampleRate * 0.04))
  }
  const source = ctx.createBufferSource()
  source.buffer = buffer
  const filter = ctx.createBiquadFilter()
  filter.type = "lowpass"
  filter.frequency.value = 800
  const gain = ctx.createGain()
  gain.gain.value = 0.1
  source.connect(filter).connect(gain).connect(dest)
  source.start()
}

function playAllInSound(ctx: AudioContext, dest: GainNode) {
  const osc = ctx.createOscillator()
  osc.type = "sine"
  osc.frequency.setValueAtTime(400, ctx.currentTime)
  osc.frequency.linearRampToValueAtTime(800, ctx.currentTime + 0.15)
  const gain = ctx.createGain()
  gain.gain.setValueAtTime(0.12, ctx.currentTime)
  gain.gain.linearRampToValueAtTime(0, ctx.currentTime + 0.2)
  osc.connect(gain).connect(dest)
  osc.start()
  osc.stop(ctx.currentTime + 0.2)
}

function playFoldSound(ctx: AudioContext, dest: GainNode) {
  const duration = 0.08
  const buffer = ctx.createBuffer(1, ctx.sampleRate * duration, ctx.sampleRate)
  const data = buffer.getChannelData(0)
  for (let i = 0; i < data.length; i++) {
    data[i] = (Math.random() * 2 - 1) * Math.exp(-i / (ctx.sampleRate * 0.02))
  }
  const source = ctx.createBufferSource()
  source.buffer = buffer
  const filter = ctx.createBiquadFilter()
  filter.type = "lowpass"
  filter.frequency.value = 500
  const gain = ctx.createGain()
  gain.gain.value = 0.08
  source.connect(filter).connect(gain).connect(dest)
  source.start()
}

function playCheckSound(ctx: AudioContext, dest: GainNode) {
  const playKnock = (delay: number) => {
    const duration = 0.03
    const buffer = ctx.createBuffer(1, ctx.sampleRate * duration, ctx.sampleRate)
    const data = buffer.getChannelData(0)
    for (let i = 0; i < data.length; i++) {
      data[i] = (Math.random() * 2 - 1) * Math.exp(-i / (ctx.sampleRate * 0.006))
    }
    const source = ctx.createBufferSource()
    source.buffer = buffer
    const filter = ctx.createBiquadFilter()
    filter.type = "bandpass"
    filter.frequency.value = 1200
    filter.Q.value = 2
    const gain = ctx.createGain()
    gain.gain.value = 0.1
    source.connect(filter).connect(gain).connect(dest)
    source.start(ctx.currentTime + delay)
  }
  playKnock(0)
  playKnock(0.07)
}
