"use client"

export default function MainError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center px-6 text-center">
      <h2 className="mb-4 font-display text-3xl font-bold text-mc-white">
        Something went wrong
      </h2>
      <p className="mb-8 max-w-md text-sm text-mc-white/50">
        {error.message || "An unexpected error occurred."}
      </p>
      <button
        onClick={reset}
        className="rounded-lg bg-crimson px-6 py-2.5 font-headline text-sm tracking-[0.2em] text-mc-white transition-colors hover:bg-red-bright"
      >
        TRY AGAIN
      </button>
    </div>
  )
}
