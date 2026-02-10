"use client"

import { useState } from "react"
import Image from "next/image"
import Link from "next/link"
import { XIcon, GitHubIcon, TelegramIcon } from "@/components/icons"

const NAV_LINKS = [
	{ label: "DOCS", href: "/docs" },
	{ label: "LEADERBOARD", href: "/leaderboard" },
	{ label: "GAMES", href: "/games" },
] as const

const SOCIAL_LINKS = [
	{ label: "X", href: "https://x.com/monteclaude", icon: <XIcon /> },
	{ label: "GitHub", href: "https://github.com/monteclaude", icon: <GitHubIcon /> },
	{ label: "Telegram", href: "https://t.me/monteclaude", icon: <TelegramIcon /> },
] as const

export function Nav() {
	const [mobileOpen, setMobileOpen] = useState(false)

	return (
		<nav className="fixed top-0 right-0 left-0 z-40 border-b border-gold/10 bg-navy">
			<div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
				<Link href="/" className="flex items-center gap-2.5">
					<Image
						src="/logo.png"
						alt="MonteClaude logo"
						width={36}
						height={36}
						sizes="36px"
						className="rounded-full"
						priority
					/>
					<span className="font-display text-xl font-medium text-mc-white">
						MonteClaude
					</span>
				</Link>

				<div className="flex items-center gap-6">
					{/* Nav links — desktop */}
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

					{/* Social icons — desktop */}
					<div className="hidden items-center gap-2 md:flex">
						{SOCIAL_LINKS.map((social) => (
							<a
								key={social.label}
								href={social.href}
								target="_blank"
								rel="noopener noreferrer"
								className="flex h-8 w-8 items-center justify-center rounded-md text-mc-white/40 transition-colors hover:text-gold"
								aria-label={social.label}
							>
								{social.icon}
							</a>
						))}
					</div>

					{/* Watch Live CTA */}
					<Link
						href="/games"
						className="flex items-center gap-2 rounded-lg bg-crimson px-5 py-2 font-headline text-sm tracking-[0.2em] text-mc-white transition-all hover:bg-red-bright hover:shadow-[0_0_20px_oklch(from_#B2171D_l_c_h_/_0.4)]"
					>
						<span className="live-dot inline-block h-2 w-2 rounded-full bg-red-400" />
						WATCH LIVE
					</Link>

					{/* Hamburger — mobile */}
					<button
						className="flex h-8 w-8 items-center justify-center rounded-md text-mc-white/60 md:hidden"
						onClick={() => setMobileOpen((v) => !v)}
						aria-label={mobileOpen ? "Close menu" : "Open menu"}
						aria-expanded={mobileOpen}
					>
						{mobileOpen ? (
							<svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
								<path d="M6 6l12 12M6 18L18 6" />
							</svg>
						) : (
							<svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
								<path d="M4 6h16M4 12h16M4 18h16" />
							</svg>
						)}
					</button>
				</div>
			</div>

			{/* Mobile menu */}
			{mobileOpen && (
				<div className="border-t border-gold/10 bg-navy px-6 pb-4 md:hidden">
					<div className="flex flex-col gap-3 py-3">
						{NAV_LINKS.map((link) => (
							<Link
								key={link.href}
								href={link.href}
								onClick={() => setMobileOpen(false)}
								className="font-headline text-sm tracking-[0.3em] text-mc-white/60 transition-colors hover:text-gold"
							>
								{link.label}
							</Link>
						))}
					</div>
					<div className="flex gap-2 border-t border-gold/10 pt-3">
						{SOCIAL_LINKS.map((social) => (
							<a
								key={social.label}
								href={social.href}
								target="_blank"
								rel="noopener noreferrer"
								className="flex h-8 w-8 items-center justify-center rounded-md text-mc-white/40 transition-colors hover:text-gold"
								aria-label={social.label}
							>
								{social.icon}
							</a>
						))}
					</div>
				</div>
			)}
		</nav>
	)
}
