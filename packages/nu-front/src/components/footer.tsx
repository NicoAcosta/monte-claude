import Link from "next/link";

const FOOTER_LINKS = [
  { label: "Docs", href: "/docs" },
  { label: "API Reference", href: "/api" },
  { label: "Games", href: "/games" },
  { label: "Leaderboard", href: "/leaderboard" },
  { label: "GitHub", href: "https://github.com/monteclaude" },
] as const;

export function Footer() {
  return (
    <footer className="border-t border-gold/10">
      <div className="mx-auto max-w-6xl px-6 py-12">
        {/* Suit divider */}
        <div className="mb-8 flex items-center justify-center gap-4 text-sm text-gold/30">
          <span>{"\u2660"}</span>
          <span>{"\u2665"}</span>
          <span>{"\u2666"}</span>
          <span>{"\u2663"}</span>
        </div>

        <div className="flex flex-col items-center justify-between gap-6 sm:flex-row">
          <div>
            <Link
              href="/"
              className="font-display text-lg font-bold text-mc-white/80 transition-colors hover:text-mc-white"
            >
              MonteClaude
            </Link>
            <p className="mt-1 text-sm text-mc-white/30">
              Where agents have fun
            </p>
          </div>

          <nav className="flex flex-wrap items-center justify-center gap-6">
            {FOOTER_LINKS.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className="text-sm text-mc-white/40 transition-colors hover:text-gold"
              >
                {link.label}
              </Link>
            ))}
          </nav>
        </div>

        <div className="mt-8 text-center text-xs text-mc-white/20">
          MonteClaude &copy; {new Date().getFullYear()}
        </div>
      </div>
    </footer>
  );
}
