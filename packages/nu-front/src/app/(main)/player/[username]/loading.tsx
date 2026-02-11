export default function PlayerLoading() {
  return (
    <div className="mx-auto max-w-4xl px-6 py-12">
      <div className="mb-1 h-8 w-48 animate-pulse rounded bg-navy-light" />
      <div className="mb-10 h-4 w-32 animate-pulse rounded bg-navy-light" />
      <div className="mb-6 h-3 w-20 animate-pulse rounded bg-navy-light" />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div
            key={i}
            className="h-24 animate-pulse rounded-xl bg-navy-light/40"
          />
        ))}
      </div>
    </div>
  )
}
