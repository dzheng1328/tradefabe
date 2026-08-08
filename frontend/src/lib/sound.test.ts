import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { generateNoiseSamples, isSoundEnabled, onSoundPlayed, playSelect, setSoundEnabled } from "./sound";

describe("sound mute toggle", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("defaults to enabled", () => {
    expect(isSoundEnabled()).toBe(true);
  });

  it("persists a mute choice across calls", () => {
    setSoundEnabled(false);
    expect(isSoundEnabled()).toBe(false);
    setSoundEnabled(true);
    expect(isSoundEnabled()).toBe(true);
  });
});

describe("onSoundPlayed notifications", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("notifies listeners when a sound actually plays", () => {
    setSoundEnabled(true);
    const listener = vi.fn();
    const unsubscribe = onSoundPlayed(listener);
    playSelect();
    expect(listener).toHaveBeenCalledTimes(1);
    unsubscribe();
  });

  it("does not notify when sound is muted -- nothing is about to play", () => {
    setSoundEnabled(false);
    const listener = vi.fn();
    onSoundPlayed(listener);
    playSelect();
    expect(listener).not.toHaveBeenCalled();
  });

  it("stops notifying once unsubscribed", () => {
    setSoundEnabled(true);
    const listener = vi.fn();
    const unsubscribe = onSoundPlayed(listener);
    unsubscribe();
    playSelect();
    expect(listener).not.toHaveBeenCalled();
  });
});

describe("generateNoiseSamples", () => {
  it("produces exactly `length` samples", () => {
    expect(generateNoiseSamples(10, () => 0.5)).toHaveLength(10);
  });

  it("maps rand()=0.5 to silence (0)", () => {
    const samples = generateNoiseSamples(3, () => 0.5);
    expect(Array.from(samples)).toEqual([0, 0, 0]);
  });

  it("maps rand()=1 to the positive peak (1) and rand()=0 to the negative peak (-1)", () => {
    expect(Array.from(generateNoiseSamples(1, () => 1))).toEqual([1]);
    expect(Array.from(generateNoiseSamples(1, () => 0))).toEqual([-1]);
  });
});

// Web Audio isn't implemented in jsdom, so these node-graph assertions run against
// a hand-rolled mock AudioContext, mirroring the shape of the real API surface
// sound.ts touches (oscillator/gain/filter/buffer-source nodes with AudioParams).
class MockAudioParam {
  value = 0;
  setValueAtTime = vi.fn().mockReturnThis();
  linearRampToValueAtTime = vi.fn().mockReturnThis();
  exponentialRampToValueAtTime = vi.fn().mockReturnThis();
}
class MockOscillatorNode {
  type = "sine";
  frequency = new MockAudioParam();
  connect = vi.fn();
  start = vi.fn();
  stop = vi.fn();
}
class MockGainNode {
  gain = new MockAudioParam();
  connect = vi.fn();
}
class MockBiquadFilterNode {
  type = "lowpass";
  frequency = new MockAudioParam();
  connect = vi.fn();
}
class MockAudioBuffer {
  numberOfChannels: number;
  length: number;
  sampleRate: number;
  private data: Float32Array;
  constructor(numberOfChannels: number, length: number, sampleRate: number) {
    this.numberOfChannels = numberOfChannels;
    this.length = length;
    this.sampleRate = sampleRate;
    this.data = new Float32Array(length);
  }
  getChannelData() {
    return this.data;
  }
}
class MockBufferSourceNode {
  buffer: MockAudioBuffer | null = null;
  connect = vi.fn();
  start = vi.fn();
  stop = vi.fn();
}
class MockAudioContext {
  currentTime = 0;
  sampleRate = 44100;
  destination = {};
  createOscillator = vi.fn(() => new MockOscillatorNode());
  createGain = vi.fn(() => new MockGainNode());
  createBiquadFilter = vi.fn(() => new MockBiquadFilterNode());
  createBufferSource = vi.fn(() => new MockBufferSourceNode());
  createBuffer = vi.fn(
    (channels: number, length: number, sampleRate: number) =>
      new MockAudioBuffer(channels, length, sampleRate),
  );
}

describe("layered sound design", () => {
  let mockCtx: MockAudioContext;

  beforeEach(async () => {
    localStorage.clear();
    mockCtx = new MockAudioContext();
    (window as unknown as { AudioContext: unknown }).AudioContext = function MockCtor() {
      return mockCtx;
    };
    // sound.ts caches its AudioContext at module scope on first use, so reload the
    // module fresh for every test to get a context tied to this test's mock.
    vi.resetModules();
  });

  afterEach(() => {
    delete (window as unknown as { AudioContext?: unknown }).AudioContext;
  });

  it("playSelect layers a filtered noise burst under the tone", async () => {
    const { playSelect } = await import("./sound");
    playSelect();
    expect(mockCtx.createOscillator).toHaveBeenCalledTimes(1); // the existing blip
    expect(mockCtx.createBufferSource).toHaveBeenCalledTimes(1); // the new noise texture
    expect(mockCtx.createBiquadFilter).toHaveBeenCalledTimes(1); // shapes the noise
  });

  it("playRangeChange layers a filtered noise burst under the tone", async () => {
    const { playRangeChange } = await import("./sound");
    playRangeChange();
    expect(mockCtx.createOscillator).toHaveBeenCalledTimes(1);
    expect(mockCtx.createBufferSource).toHaveBeenCalledTimes(1);
  });

  it("playDataLanded drops to a lower, filtered thunk instead of a bright blip", async () => {
    const { playDataLanded } = await import("./sound");
    playDataLanded();
    expect(mockCtx.createOscillator).toHaveBeenCalledTimes(1);
    const osc = mockCtx.createOscillator.mock.results[0]!.value as MockOscillatorNode;
    expect(osc.frequency.value).toBeLessThan(300); // below the old bright 300Hz blip
    expect(mockCtx.createBiquadFilter).toHaveBeenCalledTimes(1); // lowpass gives it body
    const filter = mockCtx.createBiquadFilter.mock.results[0]!.value as MockBiquadFilterNode;
    expect(filter.type).toBe("lowpass");
  });

  it("stays silent and creates no nodes when sound is muted", async () => {
    setSoundEnabled(false);
    const { playSelect, playDataLanded } = await import("./sound");
    playSelect();
    playDataLanded();
    expect(mockCtx.createOscillator).not.toHaveBeenCalled();
    expect(mockCtx.createBufferSource).not.toHaveBeenCalled();
  });

  it("playIntroSettle plays a single quiet tone, quieter than the row-select blip", async () => {
    const { playIntroSettle } = await import("./sound");
    playIntroSettle();
    expect(mockCtx.createOscillator).toHaveBeenCalledTimes(1);
    const gain = mockCtx.createGain.mock.results[0]!.value as MockGainNode;
    expect(gain.gain.linearRampToValueAtTime).toHaveBeenCalled();
    const [peakGain] = gain.gain.linearRampToValueAtTime.mock.calls[0]!;
    expect(peakGain).toBeLessThan(0.05); // quieter than playSelect's 0.05 peak
  });

  it("playIntroSettle stays silent when sound is muted", async () => {
    setSoundEnabled(false);
    const { playIntroSettle } = await import("./sound");
    playIntroSettle();
    expect(mockCtx.createOscillator).not.toHaveBeenCalled();
  });
});
