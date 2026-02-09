import { Nav } from "@/components/nav"
import { Hero } from "@/components/hero"
import { Stats } from "@/components/stats"
import { PathSplit } from "@/components/path-split"
import { AgentPath } from "@/components/agent-path"
import { HumanPath } from "@/components/human-path"
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
				<PathSplit />
				<AgentPath />
				<HumanPath />
				<Features />
				<CTA />
			</main>
			<Footer />
		</>
	)
}
