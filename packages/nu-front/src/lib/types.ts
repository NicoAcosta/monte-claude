/* ── API Response Types ── */

// Lobby
export interface Game {
  id: number
  player_count: number
  player_names: string[]
  started: boolean
  game_over: boolean
  winner: string | null
  hand_number: number
  max_players: number
  token: string | null
  buy_in: number
  buy_in_display: string
  token_symbol: string | null
  funded: boolean
  mode: string
}

export interface GameListResponse {
  games: Game[]
}

export interface Stream {
  id: number
  game_id: number
  host: string
  title: string
}

export interface StreamListResponse {
  streams: Stream[]
}

// Leaderboard
export interface TokenStat {
  token_symbol: string
  total_winnings: number
  biggest_pot_won?: number
  hands_played?: number
  hands_won?: number
}

export interface LeaderboardPlayer {
  rank: number
  username: string
  games_played: number
  hands_won: number
  win_rate: number
  total_winnings: number
  biggest_pot_won: number
  token_stats: TokenStat[]
}

export interface LeaderboardResponse {
  total: number
  players: LeaderboardPlayer[]
}

export interface RecentHand {
  game_id: number
  hand_number: number
  winner_ids: number[]
  winner_names: string[]
  winning_cards: Record<string, string[]>
  result_type: "showdown" | "fold"
  pot: number
  token_symbol: string | null
  timestamp: number
}

export interface RecentHandsResponse {
  total: number
  hands: RecentHand[]
}

// Player
export interface PlayerStats {
  username: string
  games_played: number
  hands_played: number
  hands_won: number
  total_winnings: number
  biggest_pot_won: number
  token_stats: TokenStat[]
}

// Spectator
export interface SidePot {
  amount: number
}

export interface TimerInfo {
  deadline: number
}

export interface RecentAction {
  player: string
  action: string
  amount?: number
  comment?: string
}

export interface ChatMessage {
  player: string
  message: string
  timestamp: number
}

export interface SpectatorPlayer {
  id: number
  name: string
  chips: number
  current_bet: number
  is_folded: boolean
  is_all_in: boolean
  cards: string[]
  extensions_remaining: number
  is_resigned: boolean
}

export interface SpectatorState {
  state_version: number
  hand_number: number
  phase: string
  community_cards: string[]
  pot: number
  side_pots: SidePot[]
  current_turn: number | null
  dealer: number
  small_blind_player: number
  big_blind_player: number
  players: SpectatorPlayer[]
  game_over: boolean
  winner: string | null
  recent_actions: RecentAction[]
  started: boolean
  chat_log: ChatMessage[]
  timer: TimerInfo | null
  buy_in: number
  buy_in_display: string
  token_symbol: string | null
  escrow_address: string | null
  mode: string
  max_players: number
  starting_players: number
  action_timeout: number
  small_blind: number
  big_blind: number
  game_started_at: number | null
  // Stream-specific
  commentary_text?: string | null
  stream_id?: number | null
  stream_title?: string | null
  stream_host?: string | null
  stream_created_at?: number | null
}

// Funding
export interface FundingDeposit {
  address: string
  deposited: boolean
  player_name: string | null
}

export interface FundingStatus {
  all_deposited: boolean
  deposits: FundingDeposit[]
}
