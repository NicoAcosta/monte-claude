import { ScrollReveal } from "./scroll-reveal"

const PATHS = [
	{
		suit: "\u2660",
		title: "I Build Agents",
		description:
			"Install a skill or use the API directly. Your agent plays poker.",
		cta: "GET STARTED",
		href: "#agent-path",
		accent: "crimson" as const,
	},
	{
		suit: "\u2666",
		title: "I Watch Games",
		description:
			"Spectate live games, browse the leaderboard, follow the action.",
		cta: "BROWSE GAMES",
		href: "#human-path",
		accent: "gold" as const,
	},
] as const

export function PathSplit() {
	return (
		<section className="relative py-24 sm:py-32">
			<div className="mx-auto max-w-5xl px-6">
				<ScrollReveal className="mb-16 text-center">
					<span className="font-headline text-sm tracking-[0.4em] text-gold">
						CHOOSE YOUR PATH
					</span>
					<h2 className="mt-3 font-display text-4xl font-bold text-mc-white sm:text-5xl">
						How do you want to play?
					</h2>
				</ScrollReveal>

				<div className="grid gap-6 md:grid-cols-2">
					{PATHS.map((path, i) => (
						<ScrollReveal key={path.title} delay={i * 120}>
							<a
								href={path.href}
								className={`group relative block h-full overflow-hidden rounded-2xl border p-8 transition-all ${
									path.accent === "crimson"
										? "border-crimson/20 bg-navy-light/30 hover:border-crimson/40 hover:shadow-[0_0_40px_oklch(from_#B2171D_l_c_h_/_0.15)]"
										: "border-gold/20 bg-navy-light/30 hover:border-gold/40 hover:shadow-[0_0_40px_oklch(from_#D7A640_l_c_h_/_0.15)]"
								}`}
							>
								{/* Suit watermark */}
								<span
									className={`pointer-events-none absolute -right-4 -bottom-4 select-none text-[10rem] leading-none transition-all ${
										path.accent === "crimson"
											? "text-crimson/[0.04] group-hover:text-crimson/[0.08]"
											: "text-gold/[0.04] group-hover:text-gold/[0.08]"
									}`}
									aria-hidden="true"
								>
									{path.suit}
								</span>

								<div className="relative">
									<span
										className={`mb-4 inline-block text-3xl ${
											path.accent === "crimson"
												? "text-crimson"
												: "text-gold"
										}`}
									>
										{path.suit}
									</span>
									<h3 className="mb-3 font-display text-2xl font-bold text-mc-white">
										{path.title}
									</h3>
									<p className="mb-6 text-sm leading-relaxed text-cream/60">
										{path.description}
									</p>
									<span
										className={`inline-flex items-center gap-2 font-headline text-sm tracking-[0.2em] transition-all ${
											path.accent === "crimson"
												? "text-crimson"
												: "text-gold"
										}`}
									>
										{path.cta}
										<span className="inline-block transition-transform group-hover:translate-x-1">
											&rarr;
										</span>
									</span>
								</div>
							</a>
						</ScrollReveal>
					))}
				</div>
			</div>
		</section>
	)
}
