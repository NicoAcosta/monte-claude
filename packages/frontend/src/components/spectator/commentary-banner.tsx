"use client"

import { useState, useEffect, useRef } from "react"

export function CommentaryBanner({ text }: { text: string | null }) {
  const [visible, setVisible] = useState(false)
  const [displayText, setDisplayText] = useState<string | null>(text)
  const fadeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (fadeTimerRef.current) clearTimeout(fadeTimerRef.current)

    if (text) {
      setDisplayText(text)
      setVisible(true)
    } else {
      setVisible(false)
      fadeTimerRef.current = setTimeout(() => setDisplayText(null), 500)
    }

    return () => {
      if (fadeTimerRef.current) clearTimeout(fadeTimerRef.current)
    }
  }, [text])

  if (!displayText) return null

  return (
    <div
      key={displayText}
      className="flex-shrink-0 border-t border-dealer-gold/20 bg-black/45 px-6 py-2 text-center"
      style={{
        animation: visible ? "fade-slide-in 0.4s ease" : undefined,
        opacity: visible ? 1 : 0,
        transition: "opacity 0.5s ease",
      }}
    >
      <div className="mb-1 text-[9px] uppercase tracking-[1.5px] text-gold-muted">
        Commentary
      </div>
      <div className="text-sm italic leading-relaxed text-felt-text">
        {displayText}
      </div>
    </div>
  )
}
