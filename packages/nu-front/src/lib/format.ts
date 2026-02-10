const SUIT_MAP: Record<string, string> = {
  s: "\u2660",
  h: "\u2665",
  d: "\u2666",
  c: "\u2663",
}

const SUIT_COLOR: Record<string, "red" | "black"> = {
  s: "black",
  h: "red",
  d: "red",
  c: "black",
}

const RANK_MAP: Record<string, string> = {
  A: "A", K: "K", Q: "Q", J: "J", T: "10",
  "9": "9", "8": "8", "7": "7", "6": "6",
  "5": "5", "4": "4", "3": "3", "2": "2",
}

export interface ParsedCard {
  rank: string
  suit: string
  suitSymbol: string
  color: "red" | "black"
  raw: string
}

export function parseCard(code: string): ParsedCard {
  const suitChar = code.slice(-1).toLowerCase()
  const rankChar = code.slice(0, -1)
  return {
    rank: RANK_MAP[rankChar] || rankChar,
    suit: suitChar,
    suitSymbol: SUIT_MAP[suitChar] || suitChar,
    color: SUIT_COLOR[suitChar] || "black",
    raw: code,
  }
}

export function formatChips(n: number): string {
  return n.toLocaleString("en-US")
}

export function formatSignedChips(n: number): string {
  const prefix = n > 0 ? "+" : ""
  return prefix + n.toLocaleString("en-US")
}

export function formatTimeAgo(timestampSeconds: number): string {
  const now = Date.now() / 1000
  const diff = Math.max(0, now - timestampSeconds)

  if (diff < 60) return "just now"
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

export function formatDuration(totalSeconds: number): string {
  const h = Math.floor(totalSeconds / 3600)
  const m = Math.floor((totalSeconds % 3600) / 60)
  const s = Math.floor(totalSeconds % 60)

  if (h > 0) {
    return `${h}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`
  }
  return `${m}:${s.toString().padStart(2, "0")}`
}

export function getGameStatus(game: {
  game_over: boolean
  started: boolean
}): "finished" | "in-progress" | "waiting" {
  if (game.game_over) return "finished"
  if (game.started) return "in-progress"
  return "waiting"
}

// ── Spoken card names (for TTS narration) ──

const RANK_SPOKEN: Record<string, string> = {
  A: "Ace", K: "King", Q: "Queen", J: "Jack", T: "10",
  "9": "9", "8": "8", "7": "7", "6": "6",
  "5": "5", "4": "4", "3": "3", "2": "2",
}

const SUIT_SPOKEN: Record<string, string> = {
  s: "spades", h: "hearts", d: "diamonds", c: "clubs",
}

export function cardToSpokenName(code: string): string {
  const suitChar = code.slice(-1).toLowerCase()
  const rankChar = code.slice(0, -1)
  const rank = RANK_SPOKEN[rankChar] || rankChar
  const suit = SUIT_SPOKEN[suitChar] || suitChar
  return `${rank} of ${suit}`
}

export function cardsToSpokenList(codes: string[]): string {
  if (codes.length === 0) return ""
  if (codes.length === 1) return cardToSpokenName(codes[0])
  if (codes.length === 2) {
    return `${cardToSpokenName(codes[0])} and ${cardToSpokenName(codes[1])}`
  }
  const last = codes[codes.length - 1]
  const rest = codes.slice(0, -1).map(cardToSpokenName).join(", ")
  return `${rest}, and ${cardToSpokenName(last)}`
}
