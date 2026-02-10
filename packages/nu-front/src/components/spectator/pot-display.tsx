import { formatChips } from "@/lib/format"
import type { SidePot } from "@/lib/types"

export function PotDisplay({
  pot,
  sidePots,
}: {
  pot: number
  sidePots: SidePot[]
}) {
  return (
    <div className="flex flex-col items-center gap-0.5">
      <div
        className="text-[22px] font-bold tracking-wide text-[#d4a843]"
        style={{ textShadow: "0 2px 8px rgba(0,0,0,.5)" }}
      >
        {formatChips(pot)}
      </div>
      <div className="text-[10px] uppercase tracking-[1.5px] text-[#8a9a7c]">
        Pot
      </div>

      {sidePots.length > 0 && (
        <div className="mt-0.5 flex flex-wrap justify-center gap-2">
          {sidePots.map((sp, i) => (
            <span
              key={i}
              className="rounded-full border border-[#d4a843]/20 bg-black/35 px-2 py-0.5 text-[11px] text-[#a17e2f]"
            >
              {formatChips(sp.amount)}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
