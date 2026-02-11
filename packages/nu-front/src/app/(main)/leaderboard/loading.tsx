export default function LeaderboardLoading() {
  return (
    <div className="mx-auto max-w-5xl px-6 py-12">
      <div className="mb-10">
        <div className="h-8 w-48 animate-pulse rounded bg-navy-light" />
        <div className="mt-2 h-4 w-64 animate-pulse rounded bg-navy-light" />
      </div>
      <div className="overflow-hidden rounded-xl border border-white/8 bg-navy-light/40">
        {Array.from({ length: 8 }).map((_, i) => (
          <div
            key={i}
            className="flex items-center gap-4 border-b border-white/3 px-4 py-3"
          >
            <div className="h-4 w-6 animate-pulse rounded bg-navy-light" />
            <div className="h-4 w-24 animate-pulse rounded bg-navy-light" />
            <div className="ml-auto h-4 w-16 animate-pulse rounded bg-navy-light" />
          </div>
        ))}
      </div>
    </div>
  )
}
