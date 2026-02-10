type GameStatus = "waiting" | "in-progress" | "finished"

const STYLES: Record<GameStatus, string> = {
  waiting:
    "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  "in-progress":
    "bg-amber-500/10 text-amber-400 border-amber-500/20",
  finished:
    "bg-white/5 text-white/40 border-white/10",
}

const LABELS: Record<GameStatus, string> = {
  waiting: "Waiting",
  "in-progress": "In Progress",
  finished: "Finished",
}

export function StatusBadge({ status }: { status: GameStatus }) {
  return (
    <span
      className={`inline-block rounded-full border px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${STYLES[status]}`}
    >
      {LABELS[status]}
    </span>
  )
}
