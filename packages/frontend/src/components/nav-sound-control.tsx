"use client"

import { useState } from "react"
import { useSoundContext } from "@/lib/sound-context"
import { SpeakerOnIcon, SpeakerOffIcon, EqualizerIcon } from "@/components/icons"
import { SoundMixer } from "@/components/spectator/sound-mixer"

export function NavSoundControl() {
  const { settings, toggleMaster, toggleChannel, setChannelVolume } = useSoundContext()
  const [mixerOpen, setMixerOpen] = useState(false)

  return (
    <div className="relative flex items-center gap-1">
      {/* Master toggle */}
      <button
        onClick={toggleMaster}
        className={`flex h-8 w-8 items-center justify-center rounded-md transition-colors ${
          settings.master
            ? "text-gold"
            : "text-mc-white/40 hover:text-gold"
        }`}
        title={settings.master ? "Mute all sound" : "Enable sound"}
        aria-label="Toggle all sound"
      >
        {settings.master ? (
          <SpeakerOnIcon className="h-4 w-4" />
        ) : (
          <SpeakerOffIcon className="h-4 w-4" />
        )}
      </button>

      {/* Mixer toggle */}
      <button
        onClick={() => setMixerOpen((v) => !v)}
        className={`flex h-8 w-8 items-center justify-center rounded-md transition-colors ${
          mixerOpen
            ? "text-gold"
            : "text-mc-white/40 hover:text-gold"
        }`}
        title="Sound mixer"
        aria-label="Open sound mixer"
        aria-expanded={mixerOpen}
        aria-haspopup="dialog"
      >
        <EqualizerIcon className="h-3.5 w-3.5" />
      </button>

      {/* Mixer popover */}
      <SoundMixer
        settings={settings}
        onToggleChannel={toggleChannel}
        onSetVolume={setChannelVolume}
        open={mixerOpen}
        onClose={() => setMixerOpen(false)}
      />
    </div>
  )
}
