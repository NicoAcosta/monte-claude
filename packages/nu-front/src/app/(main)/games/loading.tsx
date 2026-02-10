export default function GamesLoading() {
  return (
    <div className="mx-auto max-w-5xl px-6 py-12">
      <div className="mb-8">
        <div className="h-8 w-40 animate-pulse rounded bg-navy-light" />
        <div className="mt-2 h-4 w-24 animate-pulse rounded bg-navy-light" />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div
            key={i}
            className="h-40 animate-pulse rounded-xl bg-navy-light/40"
          />
        ))}
      </div>
    </div>
  )
}
