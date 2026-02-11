"use client"

import { useEffect, useState } from "react"
import { createPortal } from "react-dom"
import { useWarpTransition } from "./use-warp-transition"
import { WarpCanvas } from "./warp-canvas"

export function WarpTransition() {
	const { state } = useWarpTransition()
	const [mounted, setMounted] = useState(false)
	const [reducedMotion, setReducedMotion] = useState(false)

	useEffect(() => {
		setMounted(true)
		setReducedMotion(
			window.matchMedia("(prefers-reduced-motion: reduce)").matches,
		)
	}, [])

	// Block scroll while animation is active
	useEffect(() => {
		if (state !== "idle") {
			document.body.style.overflow = "hidden"
			return () => {
				document.body.style.overflow = ""
			}
		}
	}, [state])

	if (!mounted || state === "idle") return null

	// Reduced motion: simple crossfade
	if (reducedMotion) {
		return createPortal(
			<div
				className="fixed inset-0 z-[9999] bg-navy transition-opacity duration-500"
				style={{ opacity: state === "done" ? 0 : 1 }}
				role="alert"
				aria-live="assertive"
			>
				<span className="sr-only">Navigating to live games</span>
			</div>,
			document.body,
		)
	}

	return createPortal(
		<div
			className="fixed inset-0 z-[9999]"
			role="alert"
			aria-live="assertive"
		>
			<span className="sr-only">Navigating to live games</span>

			{state === "warping" && <WarpCanvas onComplete={() => {}} />}

			{state === "done" && (
				<div className="animate-[warp-flash_500ms_ease-out_forwards] fixed inset-0 bg-white" />
			)}
		</div>,
		document.body,
	)
}
