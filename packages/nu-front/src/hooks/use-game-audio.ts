"use client"

import { useEffect, useRef } from "react"
import type { GameEvent } from "@/lib/narration"

const SPEECH_RATE = 1.1
const MAX_QUEUE = 3

export function useGameAudio(
  events: GameEvent[],
  audioEnabled: boolean,
): void {
  const queueRef = useRef<GameEvent[]>([])
  const speakingRef = useRef(false)
  const audioCtxRef = useRef<AudioContext | null>(null)
  const enabledRef = useRef(audioEnabled)
  enabledRef.current = audioEnabled

  // Cancel speech when toggled off or unmount
  useEffect(() => {
    if (!audioEnabled) {
      window.speechSynthesis?.cancel()
      queueRef.current = []
      speakingRef.current = false
    }
    return () => {
      window.speechSynthesis?.cancel()
      queueRef.current = []
    }
  }, [audioEnabled])

  // Enqueue and process new events
  useEffect(() => {
    if (!audioEnabled || events.length === 0) return

    queueRef.current.push(...events)

    // If queue is too long, keep only the highest-priority events
    if (queueRef.current.length > MAX_QUEUE) {
      queueRef.current.sort((a, b) => b.priority - a.priority)
      queueRef.current = queueRef.current.slice(0, MAX_QUEUE)
    }

    // Play sound effects immediately (non-blocking)
    for (const ev of events) {
      if (ev.soundEffect) {
        playSound(ev.soundEffect, audioCtxRef)
      }
    }

    // Start speaking if not already
    if (!speakingRef.current) {
      speakNext(queueRef, speakingRef, enabledRef)
    }
  }, [events, audioEnabled])
}

function speakNext(
  queueRef: React.MutableRefObject<GameEvent[]>,
  speakingRef: React.MutableRefObject<boolean>,
  enabledRef: React.MutableRefObject<boolean>,
) {
  if (!enabledRef.current) {
    speakingRef.current = false
    return
  }

  const next = queueRef.current.shift()
  if (!next) {
    speakingRef.current = false
    return
  }

  if (typeof window === "undefined" || !window.speechSynthesis) {
    speakingRef.current = false
    return
  }

  speakingRef.current = true
  const utterance = new SpeechSynthesisUtterance(next.narration)
  utterance.rate = SPEECH_RATE
  utterance.pitch = 1
  utterance.onend = () => speakNext(queueRef, speakingRef, enabledRef)
  utterance.onerror = () => speakNext(queueRef, speakingRef, enabledRef)
  window.speechSynthesis.speak(utterance)
}

// ── Web Audio sound effects ──

function getAudioCtx(
  ref: React.MutableRefObject<AudioContext | null>,
): AudioContext | null {
  if (typeof window === "undefined") return null
  if (!ref.current) {
    try {
      ref.current = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)()
    } catch {
      return null
    }
  }
  return ref.current
}

function playSound(
  type: "deal" | "chip" | "allin",
  ctxRef: React.MutableRefObject<AudioContext | null>,
) {
  const ctx = getAudioCtx(ctxRef)
  if (!ctx) return

  switch (type) {
    case "chip":
      playChipSound(ctx)
      break
    case "deal":
      playDealSound(ctx)
      break
    case "allin":
      playAllInSound(ctx)
      break
  }
}

function playChipSound(ctx: AudioContext) {
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
  source.connect(gain).connect(ctx.destination)
  source.start()
}

function playDealSound(ctx: AudioContext) {
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
  source.connect(filter).connect(gain).connect(ctx.destination)
  source.start()
}

function playAllInSound(ctx: AudioContext) {
  const osc = ctx.createOscillator()
  osc.type = "sine"
  osc.frequency.setValueAtTime(400, ctx.currentTime)
  osc.frequency.linearRampToValueAtTime(800, ctx.currentTime + 0.15)
  const gain = ctx.createGain()
  gain.gain.setValueAtTime(0.12, ctx.currentTime)
  gain.gain.linearRampToValueAtTime(0, ctx.currentTime + 0.2)
  osc.connect(gain).connect(ctx.destination)
  osc.start()
  osc.stop(ctx.currentTime + 0.2)
}
