"use client"

import { usePoll } from "@/hooks/use-poll"
import { formatChips } from "@/lib/format"
import type { SpectatorState, FundingStatus } from "@/lib/types"

export function WaitingScreen({
  state,
  gameId,
}: {
  state: SpectatorState
  gameId: string
}) {
  const isOnchain = state.mode === "onchain"

  const { data: funding } = usePoll<FundingStatus>(
    `/api/games/${gameId}/funding`,
    5000,
    { enabled: isOnchain }
  )

  return (
    <div className="flex flex-col items-center justify-center gap-6 p-10 text-center">
      <div className="text-[28px] font-bold tracking-wider text-[#d4a843]">
        WAITING FOR PLAYERS
      </div>
      <div className="text-sm text-[#8a9a7c]">Game will begin shortly</div>

      <div className="flex max-w-[500px] flex-wrap justify-center gap-3">
        {state.players.map((p) => (
          <div
            key={p.id}
            className="min-w-[120px] rounded-lg border border-white/[0.08] bg-black/35 px-4 py-2.5"
          >
            <div className="text-sm font-semibold text-white">{p.name}</div>
            <div className="mt-0.5 text-xs font-semibold text-[#27ae60]">
              {formatChips(p.chips)}
            </div>

            {/* Funding status for on-chain games */}
            {isOnchain && funding && (
              <div className="mt-1 flex items-center gap-1.5 text-[11px]">
                {(() => {
                  const deposit = funding.deposits.find(
                    (d) => d.player_name === p.name
                  )
                  if (!deposit) return null
                  return (
                    <>
                      <span
                        className={`inline-block h-2 w-2 rounded-full ${
                          deposit.deposited
                            ? "bg-[#27ae60] shadow-[0_0_6px_rgba(39,174,96,.5)]"
                            : "animate-[dot-pulse_1s_infinite] bg-[#e74c3c]"
                        }`}
                      />
                      <span className="text-[#8a9a7c]">
                        {deposit.deposited ? "Deposited" : "Pending"}
                      </span>
                    </>
                  )
                })()}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Loading dots */}
      <div className="mt-2 flex gap-1.5">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="h-2 w-2 rounded-full bg-[#d4a843]"
            style={{
              opacity: 0.3,
              animation: "dot-pulse 1.4s ease-in-out infinite",
              animationDelay: `${i * 0.2}s`,
            }}
          />
        ))}
      </div>

      {/* Escrow link */}
      {isOnchain && state.escrow_address && (
        <a
          href={`https://basescan.org/address/${state.escrow_address}`}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-4 text-xs text-[#2980b9] no-underline hover:underline"
        >
          View escrow on Basescan &rarr;
        </a>
      )}
    </div>
  )
}
