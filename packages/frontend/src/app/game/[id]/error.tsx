"use client"

import Link from "next/link"

export default function GameError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-felt-green px-6 text-center text-cream">
      <h2 className="mb-4 font-display text-3xl font-bold">
        Failed to load game
      </h2>
      <p className="mb-8 max-w-md text-sm text-cream/50">
        {error.message || "Could not connect to the game server."}
      </p>
      <div className="flex gap-4">
        <button
          onClick={reset}
          className="rounded-lg bg-crimson px-6 py-2.5 font-headline text-sm tracking-[0.2em] text-mc-white transition-colors hover:bg-red-bright"
        >
          RETRY
        </button>
        <Link
          href="/games"
          className="rounded-lg border border-white/20 px-6 py-2.5 font-headline text-sm tracking-[0.2em] text-cream/60 transition-colors hover:border-white/40 hover:text-cream"
        >
          BACK TO GAMES
        </Link>
      </div>
    </div>
  )
}
