"use client"

import { useWarpTransition } from "./use-warp-transition"

export function WatchLiveLink({
	children,
	className,
	destination = "/games",
}: {
	children: React.ReactNode
	className?: string
	destination?: string
}) {
	const { triggerWarp, state } = useWarpTransition()

	return (
		<button
			onClick={() => state === "idle" && triggerWarp(destination)}
			className={className}
			disabled={state !== "idle"}
		>
			{children}
		</button>
	)
}
