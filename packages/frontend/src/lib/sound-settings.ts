export interface ChannelSettings {
  enabled: boolean
  volume: number // 0.0 – 1.0
}

export interface SoundSettings {
  master: boolean
  commentator: ChannelSettings
  playerComments: ChannelSettings
  effects: ChannelSettings
  ambience: ChannelSettings
}

export type SoundChannel = keyof Omit<SoundSettings, "master">

export const DEFAULT_SOUND_SETTINGS: SoundSettings = {
  master: false,
  commentator: { enabled: true, volume: 0.8 },
  playerComments: { enabled: true, volume: 0.7 },
  effects: { enabled: true, volume: 0.6 },
  ambience: { enabled: true, volume: 0.3 },
}

export const STORAGE_KEY = "monteclaude-sound-settings"

export const CHANNEL_META: Record<SoundChannel, { label: string }> = {
  commentator: { label: "Commentator" },
  playerComments: { label: "Player Talk" },
  effects: { label: "Effects" },
  ambience: { label: "Ambience" },
}

export const CHANNELS: SoundChannel[] = ["commentator", "playerComments", "effects", "ambience"]
