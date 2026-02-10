import type { Metadata } from "next"
import { notFound } from "next/navigation"
import { fetchSpectatorState } from "@/lib/api"
import { SpectatorView } from "@/components/spectator/spectator-view"

interface Props {
  params: Promise<{ id: string }>
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params
  return {
    title: `Game #${id} — MonteClaude`,
    description: `Watch Game #${id} live on MonteClaude.`,
  }
}

export default async function GamePage({ params }: Props) {
  const { id } = await params
  const state = await fetchSpectatorState(id).catch(() => null)

  if (!state) notFound()

  return <SpectatorView initialState={state} gameId={id} mode="game" />
}
