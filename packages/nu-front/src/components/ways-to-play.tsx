import { ScrollReveal } from "./scroll-reveal"

const TIERS = [
	{
		title: "Free to Play",
		badge: "NO WALLET",
		description:
			"No tokens, no wallet, no cost. Just register and play. Perfect for testing strategies and learning the game.",
		accent: "default" as const,
		cta: "Start Free",
		href: "#get-playing",
	},
	{
		title: "Fake Tokens + Faucet",
		badge: "TESTNET",
		description:
			"On-chain with MONTE tokens. Get free tokens from the faucet (10,000 MONTE/day). Real blockchain mechanics, zero financial risk.",
		accent: "gold" as const,
		cta: "Get Tokens",
		href: "#get-playing",
	},
	{
		title: "Real Tokens",
		badge: "ON-CHAIN",
		description:
			"Escrow contracts on Base. EIP-712 settlement. Trustless payouts. Play for keeps.",
		accent: "crimson" as const,
		cta: "Learn More",
		href: "/docs",
	},
] as const

export function WaysToPlay() {
	return (
		<section className="relative py-24 sm:py-32">
			<div className="mx-auto max-w-6xl px-6">
				<ScrollReveal className="mb-16 text-center">
					<span className="font-headline text-sm tracking-[0.4em] text-gold">
						WAYS TO PLAY
					</span>
					<h2 className="mt-3 font-display text-4xl font-bold text-mc-white sm:text-5xl">
						Choose Your Stakes
					</h2>
				</ScrollReveal>

				<div className="grid gap-6 md:grid-cols-3">
					{TIERS.map((tier, i) => (
						<ScrollReveal key={tier.title} delay={i * 120}>
							<div
								className={`group relative h-full overflow-hidden rounded-2xl border p-8 transition-all ${
									tier.accent === "crimson"
										? "border-crimson/25 bg-navy-light/40 hover:border-crimson/40 hover:shadow-[0_0_30px_oklch(from_#B2171D_l_c_h_/_0.12)]"
										: tier.accent === "gold"
											? "border-gold/25 bg-navy-light/40 hover:border-gold/40 hover:shadow-[0_0_30px_oklch(from_#D7A640_l_c_h_/_0.12)]"
											: "border-gold/10 bg-navy-light/30 hover:border-gold/20 hover:bg-navy-light/50"
								}`}
							>
								{/* Badge */}
								<span
									className={`mb-6 inline-block rounded-full px-3 py-1 font-headline text-[11px] tracking-[0.3em] ${
										tier.accent === "crimson"
											? "bg-crimson/15 text-crimson"
											: tier.accent === "gold"
												? "bg-gold/15 text-gold"
												: "bg-mc-white/10 text-mc-white/60"
									}`}
								>
									{tier.badge}
								</span>

								<h3 className="mb-3 font-display text-2xl font-bold text-mc-white">
									{tier.title}
								</h3>
								<p className="mb-6 text-sm leading-relaxed text-cream/60">
									{tier.description}
								</p>

								<a
									href={tier.href}
									className={`inline-flex items-center gap-1.5 text-sm font-medium transition-colors ${
										tier.accent === "crimson"
											? "text-crimson hover:text-red-bright"
											: tier.accent === "gold"
												? "text-gold hover:text-gold-light"
												: "text-mc-white/60 hover:text-mc-white"
									}`}
								>
									{tier.cta}
									<span className="inline-block transition-transform group-hover:translate-x-1">
										&rarr;
									</span>
								</a>
							</div>
						</ScrollReveal>
					))}
				</div>
			</div>
		</section>
	)
}
