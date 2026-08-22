// Short synthesized UI sounds (Web Audio oscillator blips + filtered noise bursts),
// not audio files -- nothing to source/license/commit. Real interaction moments only
// (row select, range click, first-data-landed, intro settle, scroll, and any future
// button press), never hover or re-render, per the spec. New interactive components
// (including Research Lab) should call playSelect() on their primary click/press
// action -- see ResearchLab.tsx's tab buttons for the convention: one line at the
// call site, no wrapper component needed for this few call sites. A persisted mute
// toggle is required, not optional: a tool left open all day with unmutable sound
// would get tiresome fast.
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

// Shared output bus every sound connects to instead of audioCtx.destination directly.
// A long continuous scroll firing many rapid detent clicks (or any burst of
// overlapping sounds) used to sum straight into destination with no ceiling and
// audibly CLIP (2026-08-15) -- a compressor here catches that regardless of how many
// sounds stack up, rather than each sound having to individually stay under a budget
// that's impossible to predict from a single call site.
let masterBus: GainNode | null = null;
function getMasterBus(audioCtx: AudioContext): GainNode {
  if (!masterBus) {
    const compressor = audioCtx.createDynamicsCompressor();
    compressor.threshold.value = -20;
    compressor.knee.value = 10;
    compressor.ratio.value = 10;
    compressor.attack.value = 0.003;
    compressor.release.value = 0.15;
    compressor.connect(audioCtx.destination);
    masterBus = audioCtx.createGain();
    masterBus.gain.value = 0.9;
    masterBus.connect(compressor);
  }
  return masterBus;
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
    g.connect(getMasterBus(audioCtx));
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
    g.connect(getMasterBus(audioCtx));
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
    g.connect(getMasterBus(audioCtx));
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

// ---------- scroll sound ----------
// Third pass (2026-08-15): the second redesign fixed the clicky-knob character but
// introduced a different problem -- it throttled by TIME (a flat cadence once every
// SCROLL_TICK_THROTTLE_MS), so a slow deliberate scroll and a fast flick fired ticks
// at the same tempo as long as *some* motion kept happening. What actually needs to
// track scroll amount is tick RATE, so a small scroll produces little/no sound and a
// big one produces several -- this is NOT the rejected streak/intensity ramp (no
// state persists across a pause, nothing gets louder or changes pitch the longer you
// scroll): it's a flat distance-per-tick quantum, like a wheel that clicks once every
// fixed rotation regardless of how many times you've already turned it. Every
// individual tick is still the exact same fixed-gain sound from metallicTick() below.

// Distance a scroll gesture must cover before the next identical tick fires -- purely
// mechanical (like a click-wheel's notch spacing), not a function of elapsed time.
export const SCROLL_TICK_DISTANCE_PX = 40;
// Caps how many ticks a single scroll EVENT can trigger (a scrollbar-track click or a
// Home/End jump can cover thousands of px at once) -- keeps a big jump from flooding
// the audio graph with a burst of identical ticks.
export const SCROLL_MAX_TICKS_PER_EVENT = 5;

export interface ScrollTickState {
  distanceSincePrevTick: number; // unsigned px accumulated toward the next tick
}

export function initScrollTickState(): ScrollTickState {
  return { distanceSincePrevTick: 0 };
}

// Pure so the distance-accumulation/tick-count logic is directly unit-testable
// without a DOM scroll container or an AudioContext.
export function advanceScrollTicks(
  prev: ScrollTickState,
  deltaY: number,
): { state: ScrollTickState; ticks: number } {
  const distance = prev.distanceSincePrevTick + Math.abs(deltaY);
  const rawTicks = Math.floor(distance / SCROLL_TICK_DISTANCE_PX);
  const ticks = Math.min(SCROLL_MAX_TICKS_PER_EVENT, rawTicks);
  const distanceSincePrevTick = distance - ticks * SCROLL_TICK_DISTANCE_PX;
  return { state: { distanceSincePrevTick }, ticks };
}

// One soft metallic tick: two close sine partials (inharmonic, not an octave/fifth,
// so it reads as a small metal tap rather than a musical note) through a resonant
// lowpass for a bit of ring, plus a very brief quiet noise transient underneath for
// tactile attack. Identical every time -- no direction, no intensity.
function metallicTick(startOffsetSec = 0) {
  const audioCtx = getContext();
  if (!audioCtx) return;
  try {
    const startTime = audioCtx.currentTime + startOffsetSec;
    const durationSec = 0.05;

    const filter = audioCtx.createBiquadFilter();
    filter.type = "lowpass";
    filter.frequency.value = 2400;
    filter.Q.value = 4;
    filter.connect(getMasterBus(audioCtx));

    for (const freq of [1080, 1590]) {
      const osc = audioCtx.createOscillator();
      osc.type = "sine";
      osc.frequency.value = freq;
      const g = audioCtx.createGain();
      g.gain.setValueAtTime(0, startTime);
      g.gain.linearRampToValueAtTime(0.016, startTime + 0.002);
      g.gain.exponentialRampToValueAtTime(0.0001, startTime + durationSec);
      osc.connect(g);
      g.connect(filter);
      osc.start(startTime);
      osc.stop(startTime + durationSec);
    }

    const noiseDurationSec = 0.006;
    const length = Math.max(1, Math.floor(audioCtx.sampleRate * noiseDurationSec));
    const buffer = audioCtx.createBuffer(1, length, audioCtx.sampleRate);
    buffer.getChannelData(0).set(generateNoiseSamples(length));
    const src = audioCtx.createBufferSource();
    src.buffer = buffer;
    const noiseFilter = audioCtx.createBiquadFilter();
    noiseFilter.type = "highpass";
    noiseFilter.frequency.value = 5000;
    const noiseGain = audioCtx.createGain();
    noiseGain.gain.setValueAtTime(0, startTime);
    noiseGain.gain.linearRampToValueAtTime(0.008, startTime + 0.001);
    noiseGain.gain.exponentialRampToValueAtTime(0.0001, startTime + noiseDurationSec);
    src.connect(noiseFilter);
    noiseFilter.connect(noiseGain);
    noiseGain.connect(getMasterBus(audioCtx));
    src.start(startTime);
    src.stop(startTime + noiseDurationSec);
  } catch {
    // Same guarantee as blip() -- never break the interaction it's attached to.
  }
}

let scrollTickState = initScrollTickState();

// Call with the scroll container's signed position delta on every native `scroll`
// event. Cheap to call at native event frequency: it no-ops under the mute gate and
// whenever accumulated scroll distance hasn't crossed SCROLL_TICK_DISTANCE_PX yet.
export function playScrollTick(deltaY: number) {
  if (!isSoundEnabled()) return;
  const { state, ticks } = advanceScrollTicks(scrollTickState, deltaY);
  scrollTickState = state;
  if (ticks === 0) return;
  notifySoundPlayed();
  // Stagger multiple ticks from one big jump so they read as a rapid roll, not a
  // single stacked chord.
  for (let i = 0; i < ticks; i++) {
    metallicTick(i * 0.03);
  }
}

// Exposed for tests that need a clean slate between scroll-sound scenarios.
export function resetScrollSoundState() {
  scrollTickState = initScrollTickState();
}
