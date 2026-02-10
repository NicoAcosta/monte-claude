"use client"

export function CommentaryBanner({ text }: { text: string | null }) {
  if (!text) return null

  return (
    <div
      key={text}
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
