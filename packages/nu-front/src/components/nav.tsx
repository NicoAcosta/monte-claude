import Image from "next/image";
import Link from "next/link";

const NAV_LINKS = [
  { label: "DOCS", href: "/docs" },
  { label: "LEADERBOARD", href: "/leaderboard" },
  { label: "GAMES", href: "/games" },
] as const;

export function Nav() {
  return (
    <nav className="fixed top-0 right-0 left-0 z-40 border-b border-gold/10 bg-navy">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
        <Link href="/" className="flex items-center gap-2.5">
          <Image
            src="/logo.png"
            alt="MonteClaude logo"
            width={36}
            height={36}
            className="rounded-full"
            priority
          />
          <span className="font-display text-xl font-medium text-mc-white">
            MonteClaude
          </span>
        </Link>

        <div className="flex items-center gap-8">
          <div className="hidden items-center gap-6 md:flex">
            {NAV_LINKS.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className="font-headline text-sm tracking-[0.3em] text-mc-white/60 transition-colors hover:text-gold"
              >
                {link.label}
              </Link>
            ))}
          </div>

          <Link
            href="/play"
            className="rounded-lg bg-crimson px-5 py-2 font-headline text-sm tracking-[0.2em] text-mc-white transition-all hover:bg-red-bright hover:shadow-[0_0_20px_oklch(from_#B2171D_l_c_h_/_0.4)]"
          >
            PLAY NOW
          </Link>
        </div>
      </div>
    </nav>
  );
}
