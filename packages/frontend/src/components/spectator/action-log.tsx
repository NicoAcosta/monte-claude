import { formatChips } from "@/lib/format"
import type { RecentAction } from "@/lib/types"

export function ActionLog({ actions }: { actions: RecentAction[] }) {
  return (
    <div className="flex flex-shrink-0 flex-col border-t border-white/[0.06] bg-black/35" style={{ maxHeight: 180 }}>
      <div className="flex-shrink-0 px-6 pt-2.5 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-sage">
        Action Log
      </div>
      <div className="flex-1 overflow-y-auto px-6 pb-3">
        {actions.length === 0 ? (
          <div className="py-2 text-xs text-white/20">
            No actions yet
          </div>
        ) : (
          [...actions].reverse().map((a, i) => (
            <div
              key={a.id}
              className="border-b border-white/[0.04] py-1 text-[13px] text-felt-text"
              style={{
                animation: "fade-slide-in 0.3s ease forwards",
                opacity: 0,
                animationDelay: `${i * 0.02}s`,
              }}
            >
              <span className="font-semibold text-dealer-gold">
                {a.player}
              </span>{" "}
              <span className="text-sage">{a.action}</span>
              {a.amount != null && a.amount > 0 && (
                <span className="font-semibold text-chip-green">
                  {" "}
                  {formatChips(a.amount)}
                </span>
              )}
              {a.comment && (
                <span className="ml-1 text-xs italic text-sage">
                  &ldquo;{a.comment}&rdquo;
                </span>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
