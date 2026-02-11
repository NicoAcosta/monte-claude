import type { Metadata } from "next"
import { notFound } from "next/navigation"
import { fetchStreamState } from "@/lib/api"
import { SpectatorView } from "@/components/spectator/spectator-view"

interface Props {
  params: Promise<{ id: string }>
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params
  return {
    title: `Stream #${id} — MonteClaude`,
    description: `Watch Stream #${id} live on MonteClaude.`,
  }
}

export default async function StreamPage({ params }: Props) {
  const { id } = await params
  const state = await fetchStreamState(id).catch(() => null)

  if (!state) notFound()

  return <SpectatorView initialState={state} streamId={id} mode="stream" />
}
