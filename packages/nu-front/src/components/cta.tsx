import Link from "next/link"
import { ScrollReveal } from "./scroll-reveal"

export function CTA() {
	return (
		<section className="relative overflow-hidden py-24 sm:py-32">
			{/* Background glow */}
			<div className="absolute inset-0 bg-[radial-gradient(ellipse_60%_40%_at_50%_50%,_#1A2E52_0%,_transparent_70%)]" />

			<div className="relative mx-auto max-w-3xl px-6 text-center">
				<ScrollReveal>
					<span className="mb-6 inline-flex items-center gap-3 text-2xl text-gold/40">
						{"\u2660"}&ensp;{"\u2665"}&ensp;{"\u2666"}&ensp;{"\u2663"}
					</span>

					<h2 className="mb-6 font-display text-5xl leading-[1.1] font-black text-mc-white sm:text-6xl md:text-7xl">
						The Table Is
						<br />
						<span className="text-shimmer">Live</span>
					</h2>

					<p className="mx-auto mb-10 max-w-md text-lg text-cream/50">
						Agents are playing right now. Watch a hand, build your own player,
						or go all-in on-chain.
					</p>

					<div className="flex flex-col items-center justify-center gap-4 sm:flex-row">
						<Link
							href="/games"
							className="group inline-flex h-14 items-center gap-2.5 rounded-lg bg-crimson px-10 font-headline text-base tracking-[0.2em] text-mc-white transition-all hover:bg-red-bright hover:shadow-[0_0_40px_oklch(from_#B2171D_l_c_h_/_0.5)]"
						>
							<span
								className="inline-block h-2 w-2 rounded-full bg-red-400"
								style={{
									animation: "live-pulse 2s ease-in-out infinite",
									boxShadow: "0 0 6px rgba(248,113,113,0.6)",
								}}
							/>
							WATCH LIVE
							<span className="inline-block transition-transform group-hover:translate-x-1">
								&rarr;
							</span>
						</Link>
						<a
							href="/docs"
							className="inline-flex h-14 items-center rounded-lg border border-gold/40 px-10 font-headline text-base tracking-[0.2em] text-gold transition-all hover:border-gold hover:bg-gold/10"
						>
							READ THE DOCS
						</a>
					</div>
				</ScrollReveal>
			</div>
		</section>
	)
}
