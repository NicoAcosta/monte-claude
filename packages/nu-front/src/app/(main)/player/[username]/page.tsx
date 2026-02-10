import type { Metadata } from "next"
import { notFound } from "next/navigation"
import { fetchPlayerStats } from "@/lib/api"
import { formatChips, formatSignedChips } from "@/lib/format"
import { ScrollReveal } from "@/components/scroll-reveal"

interface Props {
  params: Promise<{ username: string }>
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { username } = await params
  const decoded = decodeURIComponent(username)
  return {
    title: `${decoded} — MonteClaude`,
    description: `Player stats for ${decoded} on MonteClaude.`,
  }
}

export default async function PlayerPage({ params }: Props) {
  const { username } = await params
  const decoded = decodeURIComponent(username)
  const stats = await fetchPlayerStats(decoded)

  if (!stats) notFound()

  const winRate =
    stats.hands_played > 0
      ? ((stats.hands_won / stats.hands_played) * 100).toFixed(1)
      : "0.0"

  const statCards = [
    { label: "Games Played", value: formatChips(stats.games_played) },
    { label: "Hands Played", value: formatChips(stats.hands_played) },
    { label: "Hands Won", value: formatChips(stats.hands_won) },
    { label: "Win Rate", value: `${winRate}%` },
    {
      label: "Net Winnings",
      value: formatSignedChips(stats.total_winnings),
      colored: true,
      positive: stats.total_winnings >= 0,
    },
    { label: "Biggest Pot Won", value: formatChips(stats.biggest_pot_won) },
    ...stats.token_stats.map((t) => ({
      label: `${t.token_symbol} Net`,
      value: formatSignedChips(t.total_winnings),
      colored: true,
      positive: t.total_winnings >= 0,
    })),
  ]

  return (
    <div className="mx-auto max-w-4xl px-6 py-12">
      {/* Player header */}
      <h1 className="mb-1 font-display text-3xl font-bold text-mc-white">
        {stats.username}
      </h1>
      <p className="mb-10 text-sm text-mc-white/40">
        {formatChips(stats.games_played)} games played
      </p>

      {/* Stats grid */}
      <h2 className="mb-6 text-[10px] font-semibold uppercase tracking-[1.5px] text-mc-white/30">
        Statistics
      </h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {statCards.map((stat, i) => (
          <ScrollReveal key={stat.label} delay={i * 40}>
            <div className="rounded-xl border border-white/8 bg-navy-light/60 p-5">
              <div className="mb-2 text-[10px] uppercase tracking-wider text-mc-white/30">
                {stat.label}
              </div>
              <div
                className={`text-xl font-bold ${
                  stat.colored
                    ? stat.positive
                      ? "text-emerald-400"
                      : "text-red-400"
                    : "text-mc-white"
                }`}
              >
                {stat.value}
              </div>
            </div>
          </ScrollReveal>
        ))}
      </div>
    </div>
  )
}
