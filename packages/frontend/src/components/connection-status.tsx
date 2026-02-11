"use client"

import type { ConnectionStatus as Status } from "@/hooks/use-poll"

const LABELS: Record<Status, string> = {
  connecting: "Connecting",
  connected: "Live",
  disconnected: "Disconnected",
}

const DOT_CLASS: Record<Status, string> = {
  connecting: "loading",
  connected: "ok",
  disconnected: "err",
}

export function ConnectionStatus({ status }: { status: Status }) {
  return (
    <span className="flex items-center gap-1.5 text-xs">
      <span className={`conn-dot ${DOT_CLASS[status]}`} />
      <span className="text-[#8a9a7c]">{LABELS[status]}</span>
    </span>
  )
}
