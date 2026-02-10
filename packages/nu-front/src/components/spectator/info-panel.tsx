import type { SpectatorState } from "@/lib/types"
import { formatChips } from "@/lib/format"

export function InfoPanel({
  state,
  visible,
  gameDuration,
  streamDuration,
}: {
  state: SpectatorState
  visible: boolean
  gameDuration: string
  streamDuration: string | null
}) {
  return (
    <div
      className="overflow-hidden border-b border-white/[0.06] bg-black/45 transition-all duration-300"
      style={{
        maxHeight: visible ? 120 : 0,
        padding: visible ? "12px 24px" : "0 24px",
      }}
    >
      <div className="flex flex-wrap justify-center gap-6">
        <InfoItem label="Players" value={`${state.players.length}/${state.max_players}`} />
        <InfoItem label="Buy-in" value={state.buy_in_display || formatChips(state.buy_in)} />
        <InfoItem label="Timer" value={`${state.action_timeout}s`} />
        <InfoItem label="Mode" value={state.mode === "onchain" ? "On-chain" : "Off-chain"} />
        <InfoItem label="Blinds" value={`${formatChips(state.small_blind)} / ${formatChips(state.big_blind)}`} />
        {gameDuration && <InfoItem label="Game Time" value={gameDuration} />}
        {streamDuration && <InfoItem label="Live" value={streamDuration} />}
      </div>
    </div>
  )
}

function InfoItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col items-center gap-0.5">
      <span className="text-[9px] uppercase tracking-[1.2px] text-[#8a9a7c]">
        {label}
      </span>
      <span className="text-sm font-semibold text-[#e8e0d0]">{value}</span>
    </div>
  )
}
