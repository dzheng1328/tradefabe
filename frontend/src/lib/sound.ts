// Short synthesized UI sounds (Web Audio oscillator blips + filtered noise bursts),
// not audio files -- nothing to source/license/commit. Three real interaction moments
// only (row select, range click, first-data-landed), never hover or re-render, per the
// spec. A persisted mute toggle is required, not optional: a tool left open all day
// with unmutable sound would get tiresome fast.
const STORAGE_KEY = "tradefabe.sound.enabled";
let ctx: AudioContext | null = null;

// Lets UI (the Nav sound toggle's pulse, idea #43) react to a sound actually being
// about to play, without polling or coupling to every call site.
type SoundListener = () => void;
const soundListeners = new Set<SoundListener>();

export function onSoundPlayed(listener: SoundListener): () => void {
  soundListeners.add(listener);
  return () => soundListeners.delete(listener);
}

function notifySoundPlayed() {
  for (const listener of soundListeners) listener();
}

export function isSoundEnabled(): boolean {
  return localStorage.getItem(STORAGE_KEY) !== "off";
}

export function setSoundEnabled(on: boolean) {
  localStorage.setItem(STORAGE_KEY, on ? "on" : "off");
}

function getContext(): AudioContext | null {
  if (typeof window === "undefined" || typeof window.AudioContext === "undefined") {
    return null; // no Web Audio support -- e.g. the Vitest/jsdom test environment
  }
  if (!ctx) ctx = new AudioContext();
  return ctx;
}

// Pure so the noise texture's shape is directly unit-testable without an AudioContext.
export function generateNoiseSamples(length: number, rand: () => number = Math.random): Float32Array {
  const samples = new Float32Array(length);
  for (let i = 0; i < length; i++) samples[i] = rand() * 2 - 1;
  return samples;
}

function blip(freq: number, durationSec: number, gain: number) {
  const audioCtx = getContext();
  if (!audioCtx) return;
  try {
    const osc = audioCtx.createOscillator();
    const g = audioCtx.createGain();
    osc.type = "triangle";
    osc.frequency.value = freq;
    g.gain.setValueAtTime(0, audioCtx.currentTime);
    g.gain.linearRampToValueAtTime(gain, audioCtx.currentTime + 0.005);
    g.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + durationSec);
    osc.connect(g);
    g.connect(audioCtx.destination);
    osc.start();
    osc.stop(audioCtx.currentTime + durationSec);
  } catch {
    // A UI sound effect must never break the interaction it's attached to -- e.g. a
    // browser that hasn't unlocked audio playback yet without a user gesture.
  }
}

// A short filtered burst of noise layered under a blip, giving it a tactile "click"
// texture instead of a pure tone -- idea #11 (deeper sound design, Phase 1.2).
function noiseBurst(durationSec: number, gain: number, filterFreq: number) {
  const audioCtx = getContext();
  if (!audioCtx) return;
  try {
    const length = Math.max(1, Math.floor(audioCtx.sampleRate * durationSec));
    const buffer = audioCtx.createBuffer(1, length, audioCtx.sampleRate);
    buffer.getChannelData(0).set(generateNoiseSamples(length));
    const src = audioCtx.createBufferSource();
    src.buffer = buffer;
    const filter = audioCtx.createBiquadFilter();
    filter.type = "bandpass";
    filter.frequency.value = filterFreq;
    const g = audioCtx.createGain();
    g.gain.setValueAtTime(0, audioCtx.currentTime);
    g.gain.linearRampToValueAtTime(gain, audioCtx.currentTime + 0.003);
    g.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + durationSec);
    src.connect(filter);
    filter.connect(g);
    g.connect(audioCtx.destination);
    src.start();
    src.stop(audioCtx.currentTime + durationSec);
  } catch {
    // Same guarantee as blip() -- never break the interaction it's attached to.
  }
}

// A lower, lowpass-filtered percussive hit -- idea #12's "thunk" for data landing,
// distinct in character from the bright triangle-wave blips used elsewhere.
function thunk(freq: number, durationSec: number, gain: number) {
  const audioCtx = getContext();
  if (!audioCtx) return;
  try {
    const osc = audioCtx.createOscillator();
    const filter = audioCtx.createBiquadFilter();
    const g = audioCtx.createGain();
    osc.type = "sine";
    osc.frequency.value = freq;
    filter.type = "lowpass";
    filter.frequency.value = freq * 2;
    g.gain.setValueAtTime(0, audioCtx.currentTime);
    g.gain.linearRampToValueAtTime(gain, audioCtx.currentTime + 0.008);
    g.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + durationSec);
    osc.connect(filter);
    filter.connect(g);
    g.connect(audioCtx.destination);
    osc.start();
    osc.stop(audioCtx.currentTime + durationSec);
  } catch {
    // Same guarantee as blip() -- never break the interaction it's attached to.
  }
}

export function playSelect() {
  if (!isSoundEnabled()) return;
  notifySoundPlayed();
  blip(420, 0.06, 0.05);
  noiseBurst(0.03, 0.02, 1800);
}

export function playRangeChange() {
  if (!isSoundEnabled()) return;
  notifySoundPlayed();
  blip(560, 0.04, 0.04);
  noiseBurst(0.02, 0.015, 2400);
}

export function playDataLanded() {
  if (!isSoundEnabled()) return;
  notifySoundPlayed();
  thunk(160, 0.14, 0.045);
}

// Quiet sting on the intro sequence's settle (idea #5) -- softer and slower than any
// interaction sound, since it plays once per session unprompted rather than in
// response to a click.
export function playIntroSettle() {
  if (!isSoundEnabled()) return;
  notifySoundPlayed();
  blip(660, 0.4, 0.025);
}
