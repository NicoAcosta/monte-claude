import { formatChips } from "@/lib/format"

export function WinnerOverlay({
  winner,
}: {
  winner: string | { name: string; chips: number }
}) {
  const name = typeof winner === "string" ? winner : winner.name
  const chips = typeof winner === "object" ? winner.chips : null

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm"
      style={{ animation: "fade-slide-in 0.5s ease" }}
    >
      <div
        className="rounded-2xl border-2 border-[#d4a843] bg-gradient-to-br from-[#1a1a2e] to-[#16213e] px-16 py-10 text-center shadow-[0_0_40px_rgba(212,168,67,.3)]"
        style={{ animation: "scale-in 0.4s cubic-bezier(.34,1.56,.64,1)" }}
      >
        <div className="mb-2 text-xs uppercase tracking-[3px] text-[#8a9a7c]">
          Winner
        </div>
        <div
          className="text-4xl font-bold text-[#d4a843]"
          style={{ textShadow: "0 2px 10px rgba(212,168,67,.5)" }}
        >
          {name}
        </div>
        {chips != null && (
          <div className="mt-2 text-sm text-[#8a9a7c]">
            Won {formatChips(chips)} chips
          </div>
        )}
      </div>
    </div>
  )
}
