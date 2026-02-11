"use client"

import {
	createContext,
	useContext,
	useState,
	useCallback,
	type ReactNode,
} from "react"
import { useRouter } from "next/navigation"

export type WarpState = "idle" | "warping" | "done"

interface WarpContextValue {
	state: WarpState
	triggerWarp: (destination: string) => void
}

export const WarpContext = createContext<WarpContextValue>({
	state: "idle",
	triggerWarp: () => {},
})

export function useWarpTransition() {
	return useContext(WarpContext)
}

export function WarpProvider({ children }: { children: ReactNode }) {
	const [state, setState] = useState<WarpState>("idle")
	const router = useRouter()

	const triggerWarp = useCallback(
		(dest: string) => {
			if (state !== "idle") return
			router.prefetch(dest)
			setState("warping")

			// Navigate behind the overlay
			setTimeout(() => router.push(dest), 3000)

			// Fade out
			setTimeout(() => setState("done"), 3500)

			// Reset
			setTimeout(() => setState("idle"), 4000)
		},
		[state, router],
	)

	return (
		<WarpContext.Provider value={{ state, triggerWarp }}>
			{children}
		</WarpContext.Provider>
	)
}
