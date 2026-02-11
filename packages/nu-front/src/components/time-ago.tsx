"use client"

import { formatTimeAgo } from "@/lib/format"

export function TimeAgo({ timestamp }: { timestamp: number }) {
  return <span suppressHydrationWarning>{formatTimeAgo(timestamp)}</span>
}

export function CopyrightYear() {
  return <span suppressHydrationWarning>{new Date().getFullYear()}</span>
}
