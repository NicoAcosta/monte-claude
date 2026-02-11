"use client"

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <html lang="en">
      <body className="bg-navy text-mc-white antialiased">
        <div className="flex min-h-screen flex-col items-center justify-center px-6 text-center">
          <h1 className="mb-4 font-display text-4xl font-bold">
            Something went wrong
          </h1>
          <p className="mb-8 max-w-md text-mc-white/50">
            {error.message || "An unexpected error occurred."}
          </p>
          <button
            onClick={reset}
            className="rounded-lg bg-crimson px-6 py-2.5 font-headline text-sm tracking-[0.2em] text-mc-white transition-colors hover:bg-red-bright"
          >
            TRY AGAIN
          </button>
        </div>
      </body>
    </html>
  )
}
