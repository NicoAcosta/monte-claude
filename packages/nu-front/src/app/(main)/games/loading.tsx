export default function GamesLoading() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-10">
      {/* Header skeleton */}
      <div className="mb-6">
        <div className="h-9 w-48 animate-pulse rounded bg-navy-light/60" />
        <div className="mt-3 flex gap-2">
          <div className="h-7 w-20 animate-pulse rounded-full bg-navy-light/40" />
          <div className="h-7 w-24 animate-pulse rounded-full bg-navy-light/40" />
          <div className="h-7 w-22 animate-pulse rounded-full bg-navy-light/40" />
        </div>
      </div>

      {/* Ticker skeleton */}
      <div className="mb-6 h-9 animate-pulse rounded-lg border border-white/3 bg-navy-light/20" />

      {/* Featured card skeleton */}
      <div className="mb-6 h-28 animate-pulse rounded-xl border border-white/5 bg-navy-light/40" />

      {/* Tabs skeleton */}
      <div className="mb-4 flex gap-4 border-b border-white/5 pb-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="h-4 w-12 animate-pulse rounded bg-navy-light/30"
          />
        ))}
      </div>

      {/* Grid skeletons */}
      <div className="grid gap-3 sm:gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div
            key={i}
            className="h-44 animate-pulse rounded-xl border border-white/3 bg-navy-light/30"
            style={{ animationDelay: `${i * 0.1}s` }}
          />
        ))}
      </div>
    </div>
  )
}
