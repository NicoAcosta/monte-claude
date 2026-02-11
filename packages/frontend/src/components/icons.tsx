export function XIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
    </svg>
  )
}

export function GitHubIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
    </svg>
  )
}

export function TelegramIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.479.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z" />
    </svg>
  )
}

/* ── Sound UI Icons ── */

export function SpeakerOnIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 16 16" fill="currentColor">
      <path d="M8.5 2a.5.5 0 0 1 .5.5v11a.5.5 0 0 1-.82.39L4.63 11H2.5A1.5 1.5 0 0 1 1 9.5v-3A1.5 1.5 0 0 1 2.5 5h2.13l3.55-2.89A.5.5 0 0 1 8.5 2z" />
      <path d="M11.12 5.28a.5.5 0 0 1 .7-.08 4 4 0 0 1 0 5.6.5.5 0 1 1-.62-.78 3 3 0 0 0 0-4.02.5.5 0 0 1-.08-.7z" opacity=".75" />
      <path d="M12.95 3.45a.5.5 0 0 1 .7-.05 6.5 6.5 0 0 1 0 9.2.5.5 0 1 1-.65-.76 5.5 5.5 0 0 0 0-7.68.5.5 0 0 1-.05-.7z" opacity=".5" />
    </svg>
  )
}

export function SpeakerOffIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 16 16" fill="currentColor">
      <path d="M8.5 2a.5.5 0 0 1 .5.5v11a.5.5 0 0 1-.82.39L4.63 11H2.5A1.5 1.5 0 0 1 1 9.5v-3A1.5 1.5 0 0 1 2.5 5h2.13l3.55-2.89A.5.5 0 0 1 8.5 2z" opacity=".35" />
      <path d="M13.35 5.15a.5.5 0 0 1 .7.7L12.21 7.7l1.84 1.85a.5.5 0 0 1-.7.7L11.5 8.41l-1.85 1.84a.5.5 0 0 1-.7-.7L10.79 7.7 8.95 5.85a.5.5 0 0 1 .7-.7L11.5 7l1.85-1.85z" opacity=".6" />
    </svg>
  )
}

export function MicIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 16 16" fill="currentColor">
      <rect x="5.5" y="1" width="5" height="8" rx="2.5" />
      <path d="M3.5 7a.5.5 0 0 1 .5.5A4 4 0 0 0 8 11.5a4 4 0 0 0 4-4 .5.5 0 0 1 1 0 5 5 0 0 1-4.5 4.975V14h2a.5.5 0 0 1 0 1h-5a.5.5 0 0 1 0-1h2v-1.525A5 5 0 0 1 3 7.5a.5.5 0 0 1 .5-.5z" />
    </svg>
  )
}

export function ChatBubbleIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 16 16" fill="currentColor">
      <path d="M2 2.5A1.5 1.5 0 0 1 3.5 1h9A1.5 1.5 0 0 1 14 2.5v7a1.5 1.5 0 0 1-1.5 1.5H5.37l-2.78 2.08A.5.5 0 0 1 1.8 12.8V11.2A1.5 1.5 0 0 1 2 9.5z" />
      <circle cx="5.25" cy="6" r=".85" fill="currentColor" className="opacity-40" />
      <circle cx="8" cy="6" r=".85" fill="currentColor" className="opacity-40" />
      <circle cx="10.75" cy="6" r=".85" fill="currentColor" className="opacity-40" />
    </svg>
  )
}

export function ChipSoundIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 16 16" fill="currentColor">
      <circle cx="6.5" cy="8" r="4.5" />
      <circle cx="6.5" cy="8" r="2.5" fill="currentColor" className="opacity-30" />
      <path d="M12.2 5a.5.5 0 0 1 .66-.24 .5.5 0 0 1 .24.66A5.5 5.5 0 0 1 13.1 8a5.5 5.5 0 0 1 0 2.58.5.5 0 0 1-.9-.42A4.5 4.5 0 0 0 12.2 8a4.5 4.5 0 0 0 0-2.16.5.5 0 0 1-.02-.84z" opacity=".6" />
      <path d="M14 3.6a.5.5 0 0 1 .72-.12 7 7 0 0 1 0 9.04.5.5 0 1 1-.6-.84 6 6 0 0 0 0-7.36.5.5 0 0 1-.12-.72z" opacity=".35" />
    </svg>
  )
}

export function EqualizerIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 16 16" fill="currentColor">
      <rect x="2" y="8" width="3" height="6" rx="1" />
      <rect x="6.5" y="4" width="3" height="10" rx="1" />
      <rect x="11" y="6" width="3" height="8" rx="1" />
    </svg>
  )
}
