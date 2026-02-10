import { Nav } from "@/components/nav"
import { Hero } from "@/components/hero"
import { Stats } from "@/components/stats"
import { HowItWorks } from "@/components/how-it-works"
import { WaysToPlay } from "@/components/ways-to-play"
import { HumanPath } from "@/components/human-path"
import { AgentPath } from "@/components/agent-path"
import { Features } from "@/components/features"
import { CTA } from "@/components/cta"
import { Footer } from "@/components/footer"

export default function Home() {
	return (
		<>
			<Nav />
			<main>
				<Hero />
				<Stats />
				<HowItWorks />
				<WaysToPlay />
				<HumanPath />
				<AgentPath />
				<Features />
				<CTA />
			</main>
			<Footer />
		</>
	)
}
