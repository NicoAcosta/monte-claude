"use client"

import { useEffect, useRef } from "react"

// ── Config ──
const STAR_COUNT_DESKTOP = 1200
const STAR_COUNT_MOBILE = 600
const RING_COUNT = 10
const SLIT_BAND_COUNT = 12
const DURATION = 3500 // ms total canvas time

// ── Palette ──
const NAVY = "#0C1D39"
const GOLD = "#D7A640"
const CREAM = "#F5F0E8"
const CRIMSON = "#B2171D"
const INDIGO = "#2E1065"
const VIOLET = "#6D28D9"
const CYAN = "#06B6D4"

function hexToRgb(hex: string) {
	const r = parseInt(hex.slice(1, 3), 16)
	const g = parseInt(hex.slice(3, 5), 16)
	const b = parseInt(hex.slice(5, 7), 16)
	return { r, g, b }
}

function lerpColor(
	a: { r: number; g: number; b: number },
	b: { r: number; g: number; b: number },
	t: number,
) {
	return {
		r: Math.round(a.r + (b.r - a.r) * t),
		g: Math.round(a.g + (b.g - a.g) * t),
		b: Math.round(a.b + (b.b - a.b) * t),
	}
}

// Color phase: cycles through palette over time
function getPhaseColor(elapsed: number): { r: number; g: number; b: number } {
	const cycle = (elapsed / 1500) % 4
	const colors = [hexToRgb(GOLD), hexToRgb(CRIMSON), hexToRgb(VIOLET), hexToRgb(CYAN)]
	const idx = Math.floor(cycle)
	const t = cycle - idx
	return lerpColor(colors[idx % 4], colors[(idx + 1) % 4], t)
}

// Background color phase
function getBgColor(elapsed: number): string {
	const t = Math.min(elapsed / 2500, 1)
	const navy = hexToRgb(NAVY)
	const indigo = hexToRgb(INDIGO)
	const bg = lerpColor(navy, indigo, t * 0.6)
	return `rgb(${bg.r}, ${bg.g}, ${bg.b})`
}

// ── Star System ──
interface Star {
	x: number
	y: number
	z: number
	pz: number
	speed: number
	isHero: boolean // 5% are hero stars (brighter, thicker)
}

function createStars(count: number): Star[] {
	return Array.from({ length: count }, () => ({
		x: (Math.random() - 0.5) * 2,
		y: (Math.random() - 0.5) * 2,
		z: Math.random(),
		pz: Math.random(),
		speed: 0.2 + Math.random() * 0.8,
		isHero: Math.random() < 0.05,
	}))
}

// ── Floating Objects (lobsters + chips) ──
interface FloatingObject {
	x: number
	y: number
	z: number
	pz: number
	angle: number // direction from center
	rotation: number
	rotSpeed: number
	type: "lobster" | "chip"
	variant: number // 0-3 for different looks
	speed: number
	isHero: boolean // 20% chance — larger, slower, more visible
}

function spawnObject(type: "lobster" | "chip"): FloatingObject {
	const angle = Math.random() * Math.PI * 2
	const isHero = Math.random() < 0.2
	const spread = isHero
		? 0.08 + Math.random() * 0.15 // heroes spawn closer to center
		: 0.12 + Math.random() * 0.3
	return {
		x: Math.cos(angle) * spread,
		y: Math.sin(angle) * spread,
		z: 0.7 + Math.random() * 0.2, // start closer (was 0.95-1.0)
		pz: 0.9,
		angle,
		rotation: Math.random() * Math.PI * 2,
		rotSpeed: (Math.random() - 0.5) * 0.1,
		type,
		variant: Math.floor(Math.random() * 4),
		speed: isHero ? 0.15 + Math.random() * 0.15 : 0.3 + Math.random() * 0.4,
		isHero,
	}
}

// ── Canvas Lobster Drawing ──
function drawLobster(
	ctx: CanvasRenderingContext2D,
	x: number,
	y: number,
	size: number,
	rotation: number,
	alpha: number,
) {
	ctx.save()
	ctx.translate(x, y)
	ctx.rotate(rotation)
	ctx.globalAlpha = alpha

	const s = size

	// Body
	const bodyGrad = ctx.createRadialGradient(0, 0, 0, 0, 0, s * 0.5)
	bodyGrad.addColorStop(0, CRIMSON)
	bodyGrad.addColorStop(1, "#8B1015")
	ctx.fillStyle = bodyGrad
	ctx.beginPath()
	ctx.ellipse(0, 0, s * 0.45, s * 0.28, 0, 0, Math.PI * 2)
	ctx.fill()

	// Head
	ctx.fillStyle = CRIMSON
	ctx.beginPath()
	ctx.ellipse(-s * 0.45, 0, s * 0.2, s * 0.18, 0, 0, Math.PI * 2)
	ctx.fill()

	// Eyes
	ctx.fillStyle = GOLD
	ctx.beginPath()
	ctx.arc(-s * 0.55, -s * 0.1, s * 0.04, 0, Math.PI * 2)
	ctx.arc(-s * 0.55, s * 0.1, s * 0.04, 0, Math.PI * 2)
	ctx.fill()

	// Tail segments
	ctx.fillStyle = CRIMSON
	ctx.beginPath()
	ctx.ellipse(s * 0.5, 0, s * 0.15, s * 0.12, 0, 0, Math.PI * 2)
	ctx.fill()
	ctx.beginPath()
	ctx.ellipse(s * 0.65, 0, s * 0.1, s * 0.08, 0, 0, Math.PI * 2)
	ctx.fill()
	// Tail fan
	ctx.beginPath()
	ctx.moveTo(s * 0.7, 0)
	ctx.lineTo(s * 0.85, -s * 0.1)
	ctx.lineTo(s * 0.82, 0)
	ctx.lineTo(s * 0.85, s * 0.1)
	ctx.closePath()
	ctx.fill()

	// Claws
	ctx.fillStyle = CRIMSON
	// Left claw
	ctx.beginPath()
	ctx.ellipse(-s * 0.6, -s * 0.2, s * 0.14, s * 0.08, -0.4, 0, Math.PI * 2)
	ctx.fill()
	// Claw pincer top
	ctx.beginPath()
	ctx.moveTo(-s * 0.7, -s * 0.24)
	ctx.quadraticCurveTo(-s * 0.82, -s * 0.32, -s * 0.75, -s * 0.18)
	ctx.fill()
	// Right claw
	ctx.beginPath()
	ctx.ellipse(-s * 0.6, s * 0.2, s * 0.14, s * 0.08, 0.4, 0, Math.PI * 2)
	ctx.fill()
	ctx.beginPath()
	ctx.moveTo(-s * 0.7, s * 0.24)
	ctx.quadraticCurveTo(-s * 0.82, s * 0.32, -s * 0.75, s * 0.18)
	ctx.fill()

	// Antennae
	ctx.strokeStyle = CRIMSON
	ctx.lineWidth = s * 0.02
	ctx.lineCap = "round"
	ctx.beginPath()
	ctx.moveTo(-s * 0.55, -s * 0.12)
	ctx.quadraticCurveTo(-s * 0.75, -s * 0.35, -s * 0.85, -s * 0.4)
	ctx.stroke()
	ctx.beginPath()
	ctx.moveTo(-s * 0.55, s * 0.12)
	ctx.quadraticCurveTo(-s * 0.75, s * 0.35, -s * 0.85, s * 0.4)
	ctx.stroke()

	// Legs (4 pairs)
	for (let i = 0; i < 4; i++) {
		const lx = -s * 0.15 + i * s * 0.15
		ctx.beginPath()
		ctx.moveTo(lx, -s * 0.25)
		ctx.lineTo(lx - s * 0.05, -s * 0.4)
		ctx.stroke()
		ctx.beginPath()
		ctx.moveTo(lx, s * 0.25)
		ctx.lineTo(lx - s * 0.05, s * 0.4)
		ctx.stroke()
	}

	// Gold edge highlight
	ctx.strokeStyle = `rgba(215, 166, 64, ${alpha * 0.4})`
	ctx.lineWidth = s * 0.015
	ctx.beginPath()
	ctx.ellipse(0, 0, s * 0.46, s * 0.29, 0, 0, Math.PI * 2)
	ctx.stroke()

	ctx.globalAlpha = 1
	ctx.restore()
}

// ── Canvas Poker Chip Drawing ──
function drawChip(
	ctx: CanvasRenderingContext2D,
	x: number,
	y: number,
	size: number,
	rotation: number,
	alpha: number,
	variant: number,
) {
	ctx.save()
	ctx.translate(x, y)
	ctx.rotate(rotation)
	ctx.globalAlpha = alpha

	const r = size * 0.4
	const colors = [GOLD, CRIMSON, "#E8C36A", "#8B1015"]
	const mainColor = colors[variant % 4]
	const edgeColor = variant % 2 === 0 ? CREAM : GOLD

	// Chip body (ellipse for 3D angle feel)
	ctx.fillStyle = mainColor
	ctx.beginPath()
	ctx.ellipse(0, 0, r, r * 0.7, 0, 0, Math.PI * 2)
	ctx.fill()

	// Edge stripes (8 notches around)
	ctx.fillStyle = edgeColor
	for (let i = 0; i < 8; i++) {
		const a = (i / 8) * Math.PI * 2
		ctx.beginPath()
		ctx.ellipse(
			Math.cos(a) * r * 0.85,
			Math.sin(a) * r * 0.7 * 0.85,
			r * 0.08,
			r * 0.06,
			a,
			0,
			Math.PI * 2,
		)
		ctx.fill()
	}

	// Inner circle
	ctx.strokeStyle = edgeColor
	ctx.lineWidth = size * 0.02
	ctx.beginPath()
	ctx.ellipse(0, 0, r * 0.6, r * 0.6 * 0.7, 0, 0, Math.PI * 2)
	ctx.stroke()

	// Center emblem (dollar/diamond)
	ctx.fillStyle = edgeColor
	ctx.font = `bold ${size * 0.22}px serif`
	ctx.textAlign = "center"
	ctx.textBaseline = "middle"
	ctx.fillText(variant % 2 === 0 ? "$" : "\u2666", 0, 0)

	// Edge glow
	ctx.strokeStyle = `rgba(215, 166, 64, ${alpha * 0.3})`
	ctx.lineWidth = size * 0.015
	ctx.beginPath()
	ctx.ellipse(0, 0, r * 1.02, r * 0.7 * 1.02, 0, 0, Math.PI * 2)
	ctx.stroke()

	ctx.globalAlpha = 1
	ctx.restore()
}

// ── Warp Speed Curve ──
function getWarpSpeed(elapsed: number): number {
	if (elapsed < 200) return 0.05 + (elapsed / 200) * 0.15
	if (elapsed < 800) {
		const t = (elapsed - 200) / 600
		return 0.2 + t * t * 1.8
	}
	if (elapsed < 2000) {
		const t = (elapsed - 800) / 1200
		return 2 + t * 3
	}
	if (elapsed < 2800) {
		return 5 + ((elapsed - 2000) / 800) * 2
	}
	// Deceleration into white flash
	return 7
}

// ── Main Component ──
export function WarpCanvas({ onComplete }: { onComplete: () => void }) {
	const canvasRef = useRef<HTMLCanvasElement>(null)
	const rafRef = useRef<number>(0)

	useEffect(() => {
		const canvas = canvasRef.current
		if (!canvas) return

		const ctx = canvas.getContext("2d")
		if (!ctx) return

		const isMobile = window.innerWidth < 768
		const dpr = Math.min(window.devicePixelRatio || 1, 2)

		function resize() {
			if (!canvas) return
			canvas.width = window.innerWidth * dpr
			canvas.height = window.innerHeight * dpr
			canvas.style.width = `${window.innerWidth}px`
			canvas.style.height = `${window.innerHeight}px`
		}
		resize()
		window.addEventListener("resize", resize)

		const stars = createStars(isMobile ? STAR_COUNT_MOBILE : STAR_COUNT_DESKTOP)
		const floatingObjects: FloatingObject[] = [
			spawnObject("lobster"),
			spawnObject("chip"),
			spawnObject("chip"),
		]
		let lastSpawn = 0
		const startTime = performance.now()

		function animate(time: number) {
			if (!ctx || !canvas) return

			const elapsed = time - startTime
			const w = canvas.width
			const h = canvas.height
			const cx = w / 2
			const cy = h / 2

			if (elapsed >= DURATION) {
				onComplete()
				return
			}

			const speed = getWarpSpeed(elapsed)
			const progress = elapsed / DURATION
			const phaseColor = getPhaseColor(elapsed)

			// ── Background ──
			ctx.fillStyle = getBgColor(elapsed)
			ctx.fillRect(0, 0, w, h)

			// ── Slit-Scan Light Bands (2001 Stargate) ──
			if (elapsed > 1000) {
				const bandIntensity = Math.min((elapsed - 1000) / 1000, 1) * 0.25
				const bandSpeed = speed * 0.5

				for (let i = 0; i < SLIT_BAND_COUNT; i++) {
					const phase = ((elapsed * bandSpeed * 0.0002 + i / SLIT_BAND_COUNT) % 1)
					const bandY = phase * h
					const bandH = (4 + (1 - phase) * 20) * dpr
					const bandColor = getPhaseColor(elapsed + i * 200)

					ctx.fillStyle = `rgba(${bandColor.r}, ${bandColor.g}, ${bandColor.b}, ${bandIntensity * (1 - Math.abs(phase - 0.5) * 2)})`
					ctx.fillRect(0, bandY - bandH / 2, w, bandH)

					// Mirror band (symmetry)
					ctx.fillRect(0, h - bandY - bandH / 2, w, bandH)
				}

				// Vertical slit-scan bands too for cross-hatch effect
				for (let i = 0; i < SLIT_BAND_COUNT / 2; i++) {
					const phase = ((elapsed * bandSpeed * 0.00015 + i / (SLIT_BAND_COUNT / 2)) % 1)
					const bandX = phase * w
					const bandW = (3 + (1 - phase) * 15) * dpr
					const bandColor = getPhaseColor(elapsed + i * 300 + 500)

					ctx.fillStyle = `rgba(${bandColor.r}, ${bandColor.g}, ${bandColor.b}, ${bandIntensity * 0.5 * (1 - Math.abs(phase - 0.5) * 2)})`
					ctx.fillRect(bandX - bandW / 2, 0, bandW, h)
				}
			}

			// ── Chromatic Tunnel Rings ──
			{
				const chromaticOffset = Math.min(speed * 2, 12) * dpr
				const maxRadius = Math.max(w, h) * 0.8

				for (let i = 0; i < RING_COUNT; i++) {
					const phase = ((elapsed * speed * 0.0003 + i / RING_COUNT) % 1)
					const z = 1 - phase
					if (z < 0.05) continue

					const radius = (maxRadius * 0.1) / z
					const alpha = Math.max(0, z * 0.35 * Math.min(speed / 2, 1))
					const lineW = (1 + (1 - z) * 3) * dpr

					// Red channel (offset left)
					ctx.strokeStyle = `rgba(${Math.min(phaseColor.r + 60, 255)}, ${phaseColor.g * 0.3 | 0}, ${phaseColor.b * 0.3 | 0}, ${alpha * 0.7})`
					ctx.lineWidth = lineW
					ctx.beginPath()
					ctx.ellipse(cx - chromaticOffset, cy, radius, radius * 0.55, 0, 0, Math.PI * 2)
					ctx.stroke()

					// Green/main channel (center)
					ctx.strokeStyle = `rgba(${phaseColor.r}, ${phaseColor.g}, ${phaseColor.b}, ${alpha})`
					ctx.lineWidth = lineW
					ctx.beginPath()
					ctx.ellipse(cx, cy, radius, radius * 0.55, 0, 0, Math.PI * 2)
					ctx.stroke()

					// Blue channel (offset right)
					ctx.strokeStyle = `rgba(${phaseColor.r * 0.3 | 0}, ${phaseColor.g * 0.3 | 0}, ${Math.min(phaseColor.b + 60, 255)}, ${alpha * 0.7})`
					ctx.lineWidth = lineW
					ctx.beginPath()
					ctx.ellipse(cx + chromaticOffset, cy, radius, radius * 0.55, 0, 0, Math.PI * 2)
					ctx.stroke()
				}
			}

			// ── Central Glow ──
			{
				const intensity = Math.min(speed / 5, 1)
				const glowPulse = 1 + Math.sin(elapsed * 0.005) * 0.2
				const radius = (80 + intensity * 150) * dpr * glowPulse

				const gradient = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius)
				const gc = lerpColor(hexToRgb(GOLD), { r: 255, g: 255, b: 255 }, intensity * 0.5)
				gradient.addColorStop(0, `rgba(${gc.r}, ${gc.g}, ${gc.b}, ${0.5 * intensity})`)
				gradient.addColorStop(0.4, `rgba(${gc.r}, ${gc.g}, ${gc.b}, ${0.15 * intensity})`)
				gradient.addColorStop(1, "rgba(0, 0, 0, 0)")

				ctx.fillStyle = gradient
				ctx.fillRect(cx - radius, cy - radius, radius * 2, radius * 2)
			}

			// ── Stars ──
			for (const star of stars) {
				star.pz = star.z
				star.z -= speed * star.speed * 0.006

				if (star.z < 0.001) {
					star.x = (Math.random() - 0.5) * 2
					star.y = (Math.random() - 0.5) * 2
					star.z = 1
					star.pz = 1
					continue
				}

				const sx = (star.x / star.z) * (w * 0.5) + cx
				const sy = (star.y / star.z) * (h * 0.5) + cy
				const px = (star.x / star.pz) * (w * 0.5) + cx
				const py = (star.y / star.pz) * (h * 0.5) + cy

				if (sx < -100 || sx > w + 100 || sy < -100 || sy > h + 100) continue

				const brightness = Math.min(1, (1 - star.z) * 1.5 + speed * 0.12)
				const baseSize = star.isHero ? 3 : 1.5
				const size = ((1 - star.z) * baseSize + 0.5) * dpr

				// Star color shifts with phase
				const starColor = star.isHero
					? phaseColor
					: lerpColor(hexToRgb(CREAM), phaseColor, 0.3)

				ctx.strokeStyle = `rgba(${starColor.r}, ${starColor.g}, ${starColor.b}, ${brightness})`
				ctx.lineWidth = size

				// At peak speed, hero stars draw from center for radial line effect
				if (speed > 5 && star.isHero) {
					ctx.beginPath()
					ctx.moveTo(cx + (sx - cx) * 0.3, cy + (sy - cy) * 0.3)
					ctx.lineTo(sx, sy)
					ctx.stroke()
				} else {
					ctx.beginPath()
					ctx.moveTo(px, py)
					ctx.lineTo(sx, sy)
					ctx.stroke()
				}

				// Bright head for hero stars
				if (star.isHero && brightness > 0.4) {
					ctx.fillStyle = `rgba(${starColor.r}, ${starColor.g}, ${starColor.b}, ${brightness * 0.9})`
					ctx.beginPath()
					ctx.arc(sx, sy, size * 0.8, 0, Math.PI * 2)
					ctx.fill()
				}
			}

			// ── Spawn Floating Objects ──
			const spawnInterval = elapsed > 1200 ? 120 : 200
			if (elapsed > 300 && elapsed - lastSpawn > spawnInterval) {
				const spawnChip = Math.random() < 0.5
				floatingObjects.push(spawnObject(spawnChip ? "chip" : "lobster"))
				lastSpawn = elapsed
			}

			// ── Draw Floating Objects ──
			for (let i = floatingObjects.length - 1; i >= 0; i--) {
				const obj = floatingObjects[i]

				obj.pz = obj.z
				obj.z -= speed * obj.speed * (obj.isHero ? 0.001 : 0.002)
				obj.rotation += obj.rotSpeed

				if (obj.z < 0.01) {
					floatingObjects.splice(i, 1)
					continue
				}

				const sx = (obj.x / obj.z) * (w * 0.5) + cx
				const sy = (obj.y / obj.z) * (h * 0.5) + cy

				if (sx < -200 || sx > w + 200 || sy < -200 || sy > h + 200) {
					floatingObjects.splice(i, 1)
					continue
				}

				const heroMult = obj.isHero ? 1.5 : 1
				const objSize = ((1 - obj.z) * 160 + 30) * dpr * heroMult
				const alpha = Math.min(1, (1 - obj.z) * 3 + 0.35)

				// Glow aura behind object for contrast
				const glowRadius = objSize * 0.7
				const glowGrad = ctx.createRadialGradient(sx, sy, 0, sx, sy, glowRadius)
				const glowRgb = obj.type === "lobster" ? hexToRgb(GOLD) : hexToRgb(CREAM)
				glowGrad.addColorStop(0, `rgba(${glowRgb.r}, ${glowRgb.g}, ${glowRgb.b}, ${alpha * 0.3})`)
				glowGrad.addColorStop(1, `rgba(${glowRgb.r}, ${glowRgb.g}, ${glowRgb.b}, 0)`)
				ctx.fillStyle = glowGrad
				ctx.fillRect(sx - glowRadius, sy - glowRadius, glowRadius * 2, glowRadius * 2)

				if (obj.type === "lobster") {
					drawLobster(ctx, sx, sy, objSize, obj.rotation, alpha)
				} else {
					drawChip(ctx, sx, sy, objSize, obj.rotation, alpha, obj.variant)
				}

				// Motion blur ghost (previous position, faded)
				if (speed > 2) {
					const gpx = (obj.x / obj.pz) * (w * 0.5) + cx
					const gpy = (obj.y / obj.pz) * (h * 0.5) + cy
					const ghostSize = ((1 - obj.pz) * 160 + 30) * dpr * heroMult

					if (obj.type === "lobster") {
						drawLobster(ctx, gpx, gpy, ghostSize, obj.rotation - obj.rotSpeed, alpha * 0.25)
					} else {
						drawChip(ctx, gpx, gpy, ghostSize, obj.rotation - obj.rotSpeed, alpha * 0.25, obj.variant)
					}
				}
			}

			// ── White Flash (final 700ms) ──
			if (elapsed > DURATION - 700) {
				const flashT = (elapsed - (DURATION - 700)) / 700
				const flashAlpha = flashT * flashT // ease-in quadratic
				ctx.fillStyle = `rgba(255, 255, 255, ${flashAlpha})`
				ctx.fillRect(0, 0, w, h)
			}

			rafRef.current = requestAnimationFrame(animate)
		}

		rafRef.current = requestAnimationFrame(animate)

		return () => {
			window.removeEventListener("resize", resize)
			cancelAnimationFrame(rafRef.current)
		}
	}, [onComplete])

	return (
		<canvas
			ref={canvasRef}
			className="fixed inset-0 z-[9999]"
			aria-hidden="true"
		/>
	)
}
