/**
 * Procedural casino ambient sound using Web Audio API.
 *
 * Three layers:
 *   1. Crowd murmur — filtered brown noise
 *   2. Distant chip clatter — periodic random noise bursts
 *   3. Room hum — low sine with tremolo
 */

export class CasinoAmbience {
  private ctx: AudioContext
  private output: GainNode
  private sources: AudioScheduledSourceNode[] = []
  private timers: ReturnType<typeof setTimeout>[] = []
  private running = false

  constructor(ctx: AudioContext, output: GainNode) {
    this.ctx = ctx
    this.output = output
  }

  start() {
    if (this.running) return
    this.running = true
    this.startCrowdMurmur()
    this.startRoomHum()
    this.scheduleChipClatter()
  }

  stop() {
    this.running = false
    for (const s of this.sources) {
      try { s.stop() } catch { /* already stopped */ }
    }
    this.sources = []
    for (const t of this.timers) clearTimeout(t)
    this.timers = []
  }

  isRunning() {
    return this.running
  }

  // ── Layer 1: Crowd murmur (brown noise through bandpass) ──

  private startCrowdMurmur() {
    const { ctx, output } = this
    const duration = 4 // seconds of buffer to loop
    const sampleRate = ctx.sampleRate
    const length = sampleRate * duration
    const buffer = ctx.createBuffer(1, length, sampleRate)
    const data = buffer.getChannelData(0)

    // Generate brown noise (random walk)
    let last = 0
    for (let i = 0; i < length; i++) {
      const white = Math.random() * 2 - 1
      last = (last + 0.02 * white) / 1.02
      data[i] = last * 3.5 // amplify
    }

    const source = ctx.createBufferSource()
    source.buffer = buffer
    source.loop = true

    // Bandpass for "murmur" character
    const bandpass = ctx.createBiquadFilter()
    bandpass.type = "bandpass"
    bandpass.frequency.value = 400
    bandpass.Q.value = 0.8

    // Extra lowpass to soften
    const lowpass = ctx.createBiquadFilter()
    lowpass.type = "lowpass"
    lowpass.frequency.value = 1200

    const gain = ctx.createGain()
    gain.gain.value = 0.045

    source.connect(bandpass).connect(lowpass).connect(gain).connect(output)
    source.start()
    this.sources.push(source)
  }

  // ── Layer 2: Distant chip clatter ──

  private scheduleChipClatter() {
    if (!this.running) return

    const delay = 800 + Math.random() * 2500 // 0.8s – 3.3s
    const timer = setTimeout(() => {
      if (!this.running) return
      this.playChipClatter()
      this.scheduleChipClatter()
    }, delay)
    this.timers.push(timer)
  }

  private playChipClatter() {
    const { ctx, output } = this
    const duration = 0.015 + Math.random() * 0.04 // 15ms – 55ms
    const length = Math.floor(ctx.sampleRate * duration)
    const buffer = ctx.createBuffer(1, length, ctx.sampleRate)
    const data = buffer.getChannelData(0)

    for (let i = 0; i < length; i++) {
      data[i] = (Math.random() * 2 - 1) * Math.exp(-i / (ctx.sampleRate * 0.008))
    }

    const source = ctx.createBufferSource()
    source.buffer = buffer

    const highpass = ctx.createBiquadFilter()
    highpass.type = "highpass"
    highpass.frequency.value = 2000 + Math.random() * 3000

    const gain = ctx.createGain()
    gain.gain.value = 0.008 + Math.random() * 0.012

    source.connect(highpass).connect(gain).connect(output)
    source.start()
    // Don't track these tiny one-shots in this.sources
  }

  // ── Layer 3: Room hum (low sine with tremolo) ──

  private startRoomHum() {
    const { ctx, output } = this

    const osc = ctx.createOscillator()
    osc.type = "sine"
    osc.frequency.value = 60

    // Tremolo via amplitude modulation
    const lfo = ctx.createOscillator()
    lfo.type = "sine"
    lfo.frequency.value = 0.12

    const lfoGain = ctx.createGain()
    lfoGain.gain.value = 0.004 // modulation depth

    const baseGain = ctx.createGain()
    baseGain.gain.value = 0.012

    lfo.connect(lfoGain)
    lfoGain.connect(baseGain.gain) // modulate the gain parameter

    osc.connect(baseGain).connect(output)
    osc.start()
    lfo.start()

    this.sources.push(osc, lfo)
  }
}
