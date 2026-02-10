import type { AnimationPhase } from "@/hooks/use-replay-queue"
import { CardDisplay, CardPlaceholder } from "@/components/card-display"

export function CommunityCards({
  cards,
  dealing,
  animationPhase,
}: {
  cards: string[]
  dealing: boolean
  animationPhase?: AnimationPhase
}) {
  const isRevealing = animationPhase === "community"

  const slots = []
  for (let i = 0; i < 5; i++) {
    if (i < cards.length) {
      slots.push(
        <div
          key={i}
          className={isRevealing ? "community-reveal" : ""}
          style={isRevealing ? { animationDelay: `${i * 150}ms` } : undefined}
        >
          <CardDisplay card={cards[i]} dealing={dealing && !isRevealing} />
        </div>
      )
    } else {
      slots.push(<CardPlaceholder key={i} />)
    }
  }

  return (
    <div className="flex items-center gap-2" style={{ minHeight: 76 }}>
      {slots}
    </div>
  )
}
