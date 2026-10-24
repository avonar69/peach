import { describe, expect, it } from 'vitest';
import { seekConfig, seekDelta, shortcutFromEvent, validShortcut, wheelVolume } from '../src/player/playback-preferences';

describe('independent playback preferences', () => {
  it('keeps legacy small jumps while giving all four directions independent defaults', () => {
    const config = seekConfig(undefined, 15);
    expect(seekDelta(new KeyboardEvent('keydown', { key: 'ArrowUp' }), config)).toBe(60);
    expect(seekDelta(new KeyboardEvent('keydown', { key: 'ArrowDown' }), config)).toBe(-60);
    expect(seekDelta(new KeyboardEvent('keydown', { key: 'ArrowRight' }), config)).toBe(15);
    expect(seekDelta(new KeyboardEvent('keydown', { key: 'ArrowLeft' }), config)).toBe(-15);
    config.bigForward = { seconds: 123, shortcut: 'Shift+g' };
    config.smallRewind.seconds = 7;
    expect(seekDelta(new KeyboardEvent('keydown', { key: 'G', shiftKey: true }), config)).toBe(123);
    expect(seekDelta(new KeyboardEvent('keydown', { key: 'ArrowLeft' }), config)).toBe(-7);
    expect(seekDelta(new KeyboardEvent('keydown', { key: 'ArrowUp' }), config)).toBeNull();
  });
  it('normalizes invalid amounts, reserved shortcuts and duplicate stored bindings', () => {
    const config = seekConfig({ bigForward: { seconds: -5, shortcut: 'k' }, smallForward: { seconds: Infinity, shortcut: 'ArrowUp' } });
    expect(config.bigForward.seconds).toBe(60);
    expect(config.smallForward.seconds).toBe(10);
    expect(new Set(Object.values(config).map(item => item.shortcut)).size).toBe(4);
    expect(shortcutFromEvent(new KeyboardEvent('keydown', { key: 'Tab' }))).toBe('');
    expect(validShortcut('Ctrl+Shift+w')).toBe(false);
    expect(validShortcut('Ctrl+Ctrl+g')).toBe(false);
    expect(validShortcut('Shift+g')).toBe(true);
  });
  it('changes volume only while enabled over video, clamps and removes its listener', () => {
    const root = document.createElement('div'), video = document.createElement('video');
    root.append(video); document.body.append(root);
    let enabled = false;
    const stop = wheelVolume(root, video, () => enabled);
    const wheel = (deltaY: number) => {
      const event = new WheelEvent('wheel', { deltaY, bubbles: true, cancelable: true });
      video.dispatchEvent(event); return event.defaultPrevented;
    };
    video.volume = .5;
    expect(wheel(-100)).toBe(false);
    expect(video.volume).toBe(.5);
    enabled = true; video.muted = true;
    expect(wheel(-100)).toBe(true);
    expect(video.volume).toBeCloseTo(.55);
    expect(video.muted).toBe(false);
    video.volume = 1; wheel(-100); expect(video.volume).toBe(1);
    video.volume = 0; wheel(100); expect(video.volume).toBe(0);
    stop(); expect(wheel(-100)).toBe(false); expect(video.volume).toBe(0);
    root.remove();
  });
});
