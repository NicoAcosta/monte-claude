// Stylized lobster characters for the casino reveal scene.
// Each lobster is a simple side-facing silhouette in crimson/gold.

const CRIMSON = "#B2171D"
const CRIMSON_DARK = "#8B1015"
const GOLD = "#D7A640"
const GOLD_LIGHT = "#E8C36A"

export function LobsterDealer({ className }: { className?: string }) {
	return (
		<svg
			viewBox="0 0 120 100"
			fill="none"
			xmlns="http://www.w3.org/2000/svg"
			className={className}
			aria-hidden="true"
		>
			{/* Body */}
			<ellipse cx="60" cy="58" rx="28" ry="20" fill={CRIMSON} />
			<ellipse cx="60" cy="55" rx="24" ry="16" fill={CRIMSON_DARK} />
			{/* Tail segments */}
			<ellipse cx="92" cy="62" rx="12" ry="8" fill={CRIMSON} />
			<ellipse cx="104" cy="64" rx="8" ry="5" fill={CRIMSON} />
			<path d="M110 59 L118 54 L116 64 L112 62Z" fill={CRIMSON} />
			{/* Head */}
			<ellipse cx="34" cy="50" rx="14" ry="12" fill={CRIMSON} />
			{/* Eyes */}
			<circle cx="26" cy="42" r="3" fill={GOLD} />
			<circle cx="26" cy="42" r="1.5" fill="#111" />
			{/* Antennae */}
			<path
				d="M24 40 Q14 28 8 22"
				stroke={CRIMSON}
				strokeWidth="2"
				fill="none"
				strokeLinecap="round"
			/>
			<path
				d="M28 38 Q22 24 20 16"
				stroke={CRIMSON}
				strokeWidth="2"
				fill="none"
				strokeLinecap="round"
			/>
			{/* Big claws holding cards */}
			<ellipse cx="18" cy="60" rx="10" ry="7" fill={CRIMSON} />
			<path d="M10 56 Q4 52 8 48 L14 52Z" fill={CRIMSON} />
			<path d="M10 64 Q4 68 8 72 L14 68Z" fill={CRIMSON} />
			{/* Card in claw */}
			<rect
				x="2"
				y="46"
				width="10"
				height="14"
				rx="1"
				fill="white"
				transform="rotate(-15 7 53)"
			/>
			<text
				x="5"
				y="55"
				fontSize="6"
				fill={CRIMSON}
				fontWeight="bold"
				transform="rotate(-15 7 53)"
			>
				A
			</text>
			{/* Dealer visor */}
			<path
				d="M22 42 Q34 36 44 42"
				stroke={GOLD}
				strokeWidth="3"
				fill="none"
				strokeLinecap="round"
			/>
			<path d="M22 42 L20 38 Q34 32 46 38 L44 42Z" fill={GOLD} opacity={0.9} />
			{/* Legs */}
			<path d="M48 72 L44 84" stroke={CRIMSON} strokeWidth="2.5" strokeLinecap="round" />
			<path d="M56 74 L54 86" stroke={CRIMSON} strokeWidth="2.5" strokeLinecap="round" />
			<path d="M64 74 L66 86" stroke={CRIMSON} strokeWidth="2.5" strokeLinecap="round" />
			<path d="M72 72 L76 84" stroke={CRIMSON} strokeWidth="2.5" strokeLinecap="round" />
		</svg>
	)
}

export function LobsterThinker({ className }: { className?: string }) {
	return (
		<svg
			viewBox="0 0 120 100"
			fill="none"
			xmlns="http://www.w3.org/2000/svg"
			className={className}
			aria-hidden="true"
		>
			{/* Body */}
			<ellipse cx="60" cy="58" rx="26" ry="18" fill={CRIMSON} />
			<ellipse cx="60" cy="55" rx="22" ry="14" fill={CRIMSON_DARK} />
			{/* Tail */}
			<ellipse cx="90" cy="60" rx="10" ry="7" fill={CRIMSON} />
			<ellipse cx="100" cy="62" rx="7" ry="4" fill={CRIMSON} />
			<path d="M105 58 L113 53 L111 62 L107 60Z" fill={CRIMSON} />
			{/* Head */}
			<ellipse cx="36" cy="50" rx="13" ry="11" fill={CRIMSON} />
			{/* Eyes - looking up thoughtfully */}
			<circle cx="28" cy="42" r="3" fill={GOLD} />
			<circle cx="27" cy="41" r="1.5" fill="#111" />
			{/* Antennae */}
			<path
				d="M26 40 Q18 30 14 20"
				stroke={CRIMSON}
				strokeWidth="2"
				fill="none"
				strokeLinecap="round"
			/>
			<path
				d="M30 38 Q26 26 28 16"
				stroke={CRIMSON}
				strokeWidth="2"
				fill="none"
				strokeLinecap="round"
			/>
			{/* Claw raised to chin (thinking pose) */}
			<ellipse cx="24" cy="54" rx="9" ry="6" fill={CRIMSON} />
			<path d="M16 50 Q12 46 14 42 L20 46Z" fill={CRIMSON} />
			<path d="M16 58 Q12 62 14 66 L20 62Z" fill={CRIMSON} />
			{/* Other claw on table */}
			<ellipse cx="44" cy="72" rx="8" ry="5" fill={CRIMSON} />
			{/* Chips stack next to thinker */}
			<ellipse cx="46" cy="80" rx="6" ry="2" fill={GOLD} />
			<ellipse cx="46" cy="78" rx="6" ry="2" fill={CRIMSON} />
			<ellipse cx="46" cy="76" rx="6" ry="2" fill={GOLD} />
			{/* Thought bubble */}
			<circle cx="18" cy="28" r="2" fill="white" opacity={0.5} />
			<circle cx="14" cy="22" r="3" fill="white" opacity={0.5} />
			<circle cx="8" cy="14" r="5" fill="white" opacity={0.4} />
			{/* Legs */}
			<path d="M48 70 L44 82" stroke={CRIMSON} strokeWidth="2.5" strokeLinecap="round" />
			<path d="M56 72 L54 84" stroke={CRIMSON} strokeWidth="2.5" strokeLinecap="round" />
			<path d="M64 72 L66 84" stroke={CRIMSON} strokeWidth="2.5" strokeLinecap="round" />
			<path d="M72 70 L76 82" stroke={CRIMSON} strokeWidth="2.5" strokeLinecap="round" />
		</svg>
	)
}

export function LobsterCelebrating({ className }: { className?: string }) {
	return (
		<svg
			viewBox="0 0 120 100"
			fill="none"
			xmlns="http://www.w3.org/2000/svg"
			className={className}
			aria-hidden="true"
		>
			{/* Body */}
			<ellipse cx="60" cy="58" rx="26" ry="18" fill={CRIMSON} />
			<ellipse cx="60" cy="55" rx="22" ry="14" fill={CRIMSON_DARK} />
			{/* Tail */}
			<ellipse cx="90" cy="58" rx="10" ry="7" fill={CRIMSON} />
			<ellipse cx="100" cy="60" rx="7" ry="4" fill={CRIMSON} />
			<path d="M105 56 L113 51 L111 60 L107 58Z" fill={CRIMSON} />
			{/* Head */}
			<ellipse cx="36" cy="48" rx="13" ry="11" fill={CRIMSON} />
			{/* Eyes - happy */}
			<circle cx="28" cy="42" r="3.5" fill={GOLD} />
			<circle cx="28" cy="42" r="1.5" fill="#111" />
			{/* Happy mouth */}
			<path
				d="M30 50 Q34 54 38 50"
				stroke={GOLD_LIGHT}
				strokeWidth="1.5"
				fill="none"
				strokeLinecap="round"
			/>
			{/* Antennae - raised up excitedly */}
			<path
				d="M26 38 Q16 22 10 12"
				stroke={CRIMSON}
				strokeWidth="2"
				fill="none"
				strokeLinecap="round"
			/>
			<path
				d="M30 36 Q24 18 26 8"
				stroke={CRIMSON}
				strokeWidth="2"
				fill="none"
				strokeLinecap="round"
			/>
			{/* Both claws raised up celebrating */}
			<ellipse cx="16" cy="36" rx="9" ry="6" fill={CRIMSON} transform="rotate(-30 16 36)" />
			<path d="M8 32 Q2 26 6 22 L12 28Z" fill={CRIMSON} />
			<path d="M10 40 Q4 44 6 48 L12 44Z" fill={CRIMSON} />
			<ellipse cx="20" cy="30" rx="8" ry="5" fill={CRIMSON} transform="rotate(20 20 30)" />
			{/* Sunglasses */}
			<rect x="23" y="39" width="12" height="6" rx="2" fill="#111" opacity={0.85} />
			<path d="M23 42 L18 43" stroke="#111" strokeWidth="1.5" />
			{/* Chips flying in the air */}
			<ellipse cx="10" cy="18" rx="4" ry="1.5" fill={GOLD} transform="rotate(-20 10 18)" />
			<ellipse cx="22" cy="10" rx="4" ry="1.5" fill={CRIMSON} transform="rotate(15 22 10)" />
			<ellipse cx="6" cy="8" rx="3" ry="1" fill={GOLD_LIGHT} transform="rotate(-10 6 8)" />
			{/* Legs */}
			<path d="M48 70 L44 82" stroke={CRIMSON} strokeWidth="2.5" strokeLinecap="round" />
			<path d="M56 72 L54 84" stroke={CRIMSON} strokeWidth="2.5" strokeLinecap="round" />
			<path d="M64 72 L66 84" stroke={CRIMSON} strokeWidth="2.5" strokeLinecap="round" />
			<path d="M72 70 L76 82" stroke={CRIMSON} strokeWidth="2.5" strokeLinecap="round" />
		</svg>
	)
}

export function LobsterBluffer({ className }: { className?: string }) {
	return (
		<svg
			viewBox="0 0 120 100"
			fill="none"
			xmlns="http://www.w3.org/2000/svg"
			className={className}
			aria-hidden="true"
		>
			{/* Body */}
			<ellipse cx="60" cy="58" rx="26" ry="18" fill={CRIMSON} />
			<ellipse cx="60" cy="55" rx="22" ry="14" fill={CRIMSON_DARK} />
			{/* Tail */}
			<ellipse cx="90" cy="60" rx="10" ry="7" fill={CRIMSON} />
			<ellipse cx="100" cy="62" rx="7" ry="4" fill={CRIMSON} />
			<path d="M105 58 L113 53 L111 62 L107 60Z" fill={CRIMSON} />
			{/* Head */}
			<ellipse cx="36" cy="50" rx="13" ry="11" fill={CRIMSON} />
			{/* Eyes - sneaky/squinting */}
			<ellipse cx="28" cy="43" rx="3.5" ry="2" fill={GOLD} />
			<ellipse cx="28" cy="43" rx="1.5" ry="1" fill="#111" />
			{/* Smirk */}
			<path
				d="M32 52 Q36 54 40 52"
				stroke={GOLD_LIGHT}
				strokeWidth="1.5"
				fill="none"
				strokeLinecap="round"
			/>
			{/* Antennae */}
			<path
				d="M26 40 Q18 30 14 22"
				stroke={CRIMSON}
				strokeWidth="2"
				fill="none"
				strokeLinecap="round"
			/>
			<path
				d="M30 38 Q26 26 28 18"
				stroke={CRIMSON}
				strokeWidth="2"
				fill="none"
				strokeLinecap="round"
			/>
			{/* Claw hiding cards close to body */}
			<ellipse cx="26" cy="60" rx="10" ry="7" fill={CRIMSON} />
			<path d="M18 56 Q12 52 14 48 L22 52Z" fill={CRIMSON} />
			<path d="M18 64 Q12 68 14 72 L22 68Z" fill={CRIMSON} />
			{/* Two cards face down (hiding hand) */}
			<rect x="12" y="50" width="9" height="13" rx="1" fill="#1a3a5c" transform="rotate(-5 16 56)" />
			<rect x="16" y="49" width="9" height="13" rx="1" fill="#1a3a5c" transform="rotate(5 20 55)" />
			{/* Card back pattern */}
			<rect x="14" y="52" width="5" height="9" rx="0.5" fill={GOLD} opacity={0.3} transform="rotate(-5 16 56)" />
			<rect x="18" y="51" width="5" height="9" rx="0.5" fill={GOLD} opacity={0.3} transform="rotate(5 20 55)" />
			{/* Big chip stack (bluffing with confidence) */}
			<ellipse cx="48" cy="82" rx="7" ry="2.5" fill={GOLD} />
			<ellipse cx="48" cy="80" rx="7" ry="2.5" fill={CRIMSON} />
			<ellipse cx="48" cy="78" rx="7" ry="2.5" fill={GOLD} />
			<ellipse cx="48" cy="76" rx="7" ry="2.5" fill={CRIMSON} />
			<ellipse cx="48" cy="74" rx="7" ry="2.5" fill={GOLD} />
			{/* Legs */}
			<path d="M50 70 L46 82" stroke={CRIMSON} strokeWidth="2.5" strokeLinecap="round" />
			<path d="M58 72 L56 84" stroke={CRIMSON} strokeWidth="2.5" strokeLinecap="round" />
			<path d="M66 72 L68 84" stroke={CRIMSON} strokeWidth="2.5" strokeLinecap="round" />
			<path d="M74 70 L78 82" stroke={CRIMSON} strokeWidth="2.5" strokeLinecap="round" />
		</svg>
	)
}

export function LobsterChilling({ className }: { className?: string }) {
	return (
		<svg
			viewBox="0 0 120 100"
			fill="none"
			xmlns="http://www.w3.org/2000/svg"
			className={className}
			aria-hidden="true"
		>
			{/* Body - leaned back */}
			<ellipse cx="60" cy="60" rx="26" ry="18" fill={CRIMSON} transform="rotate(-5 60 60)" />
			<ellipse cx="60" cy="57" rx="22" ry="14" fill={CRIMSON_DARK} transform="rotate(-5 60 57)" />
			{/* Tail */}
			<ellipse cx="90" cy="62" rx="10" ry="7" fill={CRIMSON} />
			<ellipse cx="100" cy="64" rx="7" ry="4" fill={CRIMSON} />
			<path d="M105 60 L113 55 L111 64 L107 62Z" fill={CRIMSON} />
			{/* Head */}
			<ellipse cx="36" cy="52" rx="13" ry="11" fill={CRIMSON} />
			{/* Eyes - relaxed/half closed */}
			<ellipse cx="28" cy="45" rx="3" ry="1.5" fill={GOLD} />
			<ellipse cx="28" cy="45" rx="1.2" ry="0.8" fill="#111" />
			{/* Content smile */}
			<path
				d="M30 52 Q34 55 38 53"
				stroke={GOLD_LIGHT}
				strokeWidth="1.2"
				fill="none"
				strokeLinecap="round"
			/>
			{/* Antennae - relaxed */}
			<path
				d="M26 42 Q20 34 16 28"
				stroke={CRIMSON}
				strokeWidth="2"
				fill="none"
				strokeLinecap="round"
			/>
			<path
				d="M30 40 Q28 30 30 24"
				stroke={CRIMSON}
				strokeWidth="2"
				fill="none"
				strokeLinecap="round"
			/>
			{/* Claw resting on table */}
			<ellipse cx="24" cy="64" rx="9" ry="6" fill={CRIMSON} />
			<path d="M16 60 Q10 56 12 52 L20 56Z" fill={CRIMSON} />
			<path d="M16 68 Q10 72 12 76 L20 72Z" fill={CRIMSON} />
			{/* Drink with tiny umbrella */}
			<rect x="6" y="54" width="8" height="12" rx="2" fill={GOLD} opacity={0.6} />
			<path d="M10 54 L10 46" stroke={GOLD_LIGHT} strokeWidth="1" />
			<path d="M10 46 L16 50 L4 50Z" fill="#E85D75" opacity={0.8} />
			{/* Small chip stack */}
			<ellipse cx="44" cy="80" rx="5" ry="1.8" fill={GOLD} />
			<ellipse cx="44" cy="78" rx="5" ry="1.8" fill={CRIMSON} />
			{/* Legs */}
			<path d="M48 72 L44 84" stroke={CRIMSON} strokeWidth="2.5" strokeLinecap="round" />
			<path d="M56 74 L54 86" stroke={CRIMSON} strokeWidth="2.5" strokeLinecap="round" />
			<path d="M64 74 L66 86" stroke={CRIMSON} strokeWidth="2.5" strokeLinecap="round" />
			<path d="M72 72 L76 84" stroke={CRIMSON} strokeWidth="2.5" strokeLinecap="round" />
		</svg>
	)
}
