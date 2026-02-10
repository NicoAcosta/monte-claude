import { parseCard } from "@/lib/format"

export function CardDisplay({
  card,
  small = false,
  dealing = false,
}: {
  card: string
  small?: boolean
  dealing?: boolean
}) {
  const { rank, suitSymbol, color } = parseCard(card)
  const sizeClass = small ? "card-small" : ""
  const colorClass = color === "red" ? "card-red" : "card-black"
  const dealClass = dealing ? "dealing" : ""

  return (
    <div className={`card ${sizeClass} ${colorClass} ${dealClass}`}>
      <span className="card-corner">
        {rank}
        <br />
        {suitSymbol}
      </span>
      <span className="card-rank">{rank}</span>
      <span className="card-suit">{suitSymbol}</span>
      <span className="card-corner-br">
        {rank}
        <br />
        {suitSymbol}
      </span>
    </div>
  )
}

export function CardBack({
  small = false,
  dealing = false,
}: {
  small?: boolean
  dealing?: boolean
}) {
  const sizeClass = small ? "card-small" : ""
  const dealClass = dealing ? "dealing" : ""
  return <div className={`card card-back ${sizeClass} ${dealClass}`} />
}

export function CardPlaceholder() {
  return <div className="card-placeholder" />
}
