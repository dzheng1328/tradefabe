// Short synthesized UI sounds (Web Audio oscillator blips), not audio files -- nothing
// to source/license/commit. Three real interaction moments only (row select, range
// click, first-data-landed), never hover or re-render, per the spec. A persisted mute
// toggle is required, not optional: a tool left open all day with unmutable sound
// would get tiresome fast.
const STORAGE_KEY = "tradefabe.sound.enabled";
let ctx: AudioContext | null = null;

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

function blip(freq: number, durationSec: number, gain: number) {
  if (!isSoundEnabled()) return;
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

export function playSelect() {
  blip(420, 0.06, 0.05);
}

export function playRangeChange() {
  blip(560, 0.04, 0.04);
}

export function playDataLanded() {
  blip(300, 0.08, 0.03);
}
