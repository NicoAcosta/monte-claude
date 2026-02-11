import type { AnimationPhase } from "@/hooks/use-replay-queue"
import { CardDisplay, CardPlaceholder } from "@/components/card-display"

export function CommunityCards({
  cards,
  dealing,
  animationPhase,
  prevCardCount = 0,
}: {
  cards: string[]
  dealing: boolean
  animationPhase?: AnimationPhase
  prevCardCount?: number
}) {
  const isRevealing = animationPhase === "community"

  const slots = []
  for (let i = 0; i < 5; i++) {
    if (i < cards.length) {
      // Only animate newly revealed cards
      const isNewCard = isRevealing && i >= prevCardCount
      // Flop: stagger 500ms per card; turn/river: no stagger (single card)
      const stagger = prevCardCount === 0 ? (i - prevCardCount) * 500 : 0
      slots.push(
        <div
          key={i}
          className={isNewCard ? "community-reveal" : ""}
          style={isNewCard ? { animationDelay: `${stagger}ms` } : undefined}
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
