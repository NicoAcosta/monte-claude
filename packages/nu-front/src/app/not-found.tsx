import Link from "next/link"

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-navy px-6 text-center">
      <h1 className="mb-2 font-display text-6xl font-black text-gold">404</h1>
      <p className="mb-8 text-lg text-mc-white/50">
        This page doesn&apos;t exist.
      </p>
      <Link
        href="/"
        className="rounded-lg bg-crimson px-6 py-2.5 font-headline text-sm tracking-[0.2em] text-mc-white transition-colors hover:bg-red-bright"
      >
        BACK TO HOME
      </Link>
    </div>
  )
}
