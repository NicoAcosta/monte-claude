"use client"

export function CommentaryBanner({ text }: { text: string | null }) {
  if (!text) return null

  return (
    <div
      key={text}
      className="flex-shrink-0 border-t border-dealer-gold/20 bg-black/45 px-6 py-2 text-center"
      style={{ animation: "fade-slide-in 0.4s ease" }}
    >
      <div className="mb-1 text-[9px] uppercase tracking-[1.5px] text-gold-muted">
        Commentary
      </div>
      <div className="text-sm italic leading-relaxed text-felt-text">
        {text}
      </div>
    </div>
  )
}
