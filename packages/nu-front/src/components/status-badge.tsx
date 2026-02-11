type GameStatus = "waiting" | "in-progress" | "finished"

const STYLES: Record<GameStatus, string> = {
  waiting:
    "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  "in-progress":
    "bg-amber-500/10 text-amber-400 border-amber-500/20",
  finished:
    "bg-white/5 text-white/25 border-white/8",
}

const LABELS: Record<GameStatus, string> = {
  waiting: "Open",
  "in-progress": "LIVE",
  finished: "Ended",
}

export function StatusBadge({ status }: { status: GameStatus }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${STYLES[status]}`}
    >
      {status === "in-progress" && (
        <span className="inline-block h-1.5 w-1.5 rounded-full bg-amber-400 live-dot" />
      )}
      {LABELS[status]}
    </span>
  )
}
