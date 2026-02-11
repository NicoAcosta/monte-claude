import Link from "next/link"
import type { Stream } from "@/lib/types"

export function StreamCard({ stream, index }: { stream: Stream; index: number }) {
  return (
    <Link
      href={`/stream/${stream.id}`}
      className="card-enter group block overflow-hidden rounded-xl border border-l-2 border-gold/10 border-l-gold/30 bg-navy-light/60 p-5 transition-all hover:border-gold/25 hover:shadow-lg"
      style={{ animationDelay: `${index * 0.06}s` }}
    >
      <div className="mb-2 flex items-center gap-2">
        <span className="inline-block h-1.5 w-1.5 rounded-full bg-red-400 live-dot" />
        <span className="font-headline text-[10px] tracking-[0.15em] text-red-400/80">
          LIVE
        </span>
      </div>
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
