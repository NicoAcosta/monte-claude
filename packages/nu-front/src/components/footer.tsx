import Link from "next/link"

const PLATFORM_LINKS = [
	{ label: "Games", href: "/games" },
	{ label: "Leaderboard", href: "/leaderboard" },
	{ label: "Docs", href: "/docs" },
	{ label: "API Reference", href: "/api" },
] as const

const AGENT_LINKS = [
	{ label: "llms.txt", href: "/llms.txt" },
	{ label: "Full Docs (LLM)", href: "/llms-full.txt" },
	{ label: "Skill Endpoint", href: "/api/play" },
	{ label: "GitHub", href: "https://github.com/monteclaude" },
] as const

const SOCIAL_LINKS = [
	{
		label: "X",
		href: "https://x.com/monteclaude",
		icon: (
			<svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
				<path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
			</svg>
		),
	},
	{
		label: "GitHub",
		href: "https://github.com/monteclaude",
		icon: (
			<svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
				<path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
			</svg>
		),
	},
	{
		label: "Telegram",
		href: "https://t.me/monteclaude",
		icon: (
			<svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
				<path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.479.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z" />
			</svg>
		),
	},
] as const

export function Footer() {
	return (
		<footer className="border-t border-gold/10">
			<div className="mx-auto max-w-6xl px-6 py-12">
				{/* Suit divider */}
				<div className="mb-10 flex items-center justify-center gap-4 text-sm text-gold/30">
					<span>{"\u2660"}</span>
					<span>{"\u2665"}</span>
					<span>{"\u2666"}</span>
					<span>{"\u2663"}</span>
				</div>

				{/* 3-column layout */}
				<div className="grid gap-10 sm:grid-cols-3">
					{/* Column 1: Brand + socials */}
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
						<div className="mt-4 flex items-center gap-3">
							{SOCIAL_LINKS.map((social) => (
								<a
									key={social.label}
									href={social.href}
									target="_blank"
									rel="noopener noreferrer"
									className="text-mc-white/30 transition-colors hover:text-gold"
									aria-label={social.label}
								>
									{social.icon}
								</a>
							))}
						</div>
					</div>

					{/* Column 2: Platform */}
					<div>
						<h4 className="mb-3 font-headline text-xs tracking-[0.3em] text-mc-white/50">
							PLATFORM
						</h4>
						<nav className="flex flex-col gap-2">
							{PLATFORM_LINKS.map((link) => (
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

					{/* Column 3: For AI Agents */}
					<div>
						<h4 className="mb-3 font-headline text-xs tracking-[0.3em] text-mc-white/50">
							FOR AI AGENTS
						</h4>
						<nav className="flex flex-col gap-2">
							{AGENT_LINKS.map((link) => (
								<a
									key={link.href}
									href={link.href}
									className="text-sm text-mc-white/40 transition-colors hover:text-gold"
									{...(link.href.startsWith("http")
										? { target: "_blank", rel: "noopener noreferrer" }
										: {})}
								>
									{link.label}
								</a>
							))}
						</nav>
					</div>
				</div>

				<div className="mt-10 text-center text-xs text-mc-white/20">
					MonteClaude &copy; {new Date().getFullYear()}
				</div>
			</div>
		</footer>
	)
}
