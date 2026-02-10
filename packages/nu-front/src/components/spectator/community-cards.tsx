import { CardDisplay, CardPlaceholder } from "@/components/card-display"

export function CommunityCards({
  cards,
  dealing,
}: {
  cards: string[]
  dealing: boolean
}) {
  const slots = []
  for (let i = 0; i < 5; i++) {
    if (i < cards.length) {
      slots.push(
        <CardDisplay key={i} card={cards[i]} dealing={dealing} />
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
