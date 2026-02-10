import Link from "next/link"
import type { Stream } from "@/lib/types"

export function StreamCard({ stream, index }: { stream: Stream; index: number }) {
  return (
    <Link
      href={`/stream/${stream.id}`}
      className="group block rounded-xl border border-gold/10 bg-navy-light/60 p-5 transition-all hover:border-gold/25 hover:shadow-lg"
      style={{ animationDelay: `${index * 0.05}s` }}
    >
      <h3 className="mb-2 font-display text-base font-bold text-mc-white">
        {stream.title}
      </h3>
      <div className="flex items-center gap-3 text-xs text-mc-white/40">
        <span>Host: {stream.host}</span>
        <span>&middot;</span>
        <span>Game #{stream.game_id}</span>
      </div>
    </Link>
  )
}
