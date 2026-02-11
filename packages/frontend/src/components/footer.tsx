import { Suspense } from "react"
import Link from "next/link"
import { XIcon, GitHubIcon, TelegramIcon } from "@/components/icons"
import { CopyrightYear } from "@/components/time-ago"

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
	{ label: "X", href: "https://x.com/monteclaude", icon: <XIcon className="h-5 w-5" /> },
	{ label: "GitHub", href: "https://github.com/monteclaude", icon: <GitHubIcon className="h-5 w-5" /> },
	{ label: "Telegram", href: "https://t.me/monteclaude", icon: <TelegramIcon className="h-5 w-5" /> },
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
					MonteClaude &copy; <Suspense><CopyrightYear /></Suspense>
				</div>
			</div>
		</footer>
	)
}
