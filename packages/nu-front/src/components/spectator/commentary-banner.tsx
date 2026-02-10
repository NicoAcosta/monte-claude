"use client"

import { useEffect, useRef } from "react"

export function CommentaryBanner({
  text,
  audioEnabled,
}: {
  text: string
  audioEnabled: boolean
}) {
  const lastSpoken = useRef("")

  useEffect(() => {
    if (!audioEnabled || !text || text === lastSpoken.current) return
    if (typeof window === "undefined" || !window.speechSynthesis) return

    lastSpoken.current = text
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.rate = 1
    utterance.pitch = 1
    window.speechSynthesis.speak(utterance)
  }, [text, audioEnabled])

  if (!text) return null

  return (
    <div
      className="flex-shrink-0 border-t border-[#d4a843]/20 bg-black/45 px-6 py-2 text-center"
      style={{ animation: "fade-slide-in 0.4s ease" }}
    >
      <div className="mb-1 text-[9px] uppercase tracking-[1.5px] text-[#a17e2f]">
        Commentary
      </div>
      <div className="text-sm italic leading-relaxed text-[#e8e0d0]">
        {text}
      </div>
    </div>
  )
}
