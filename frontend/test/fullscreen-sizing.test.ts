import { afterEach, describe, expect, it } from 'vitest';
import { fullscreenSizing, mountFullscreenSizing, setFullscreenSizing } from '../src/player/fullscreen-sizing';

afterEach(() => localStorage.removeItem('peach.player.fullscreenSizing'));
describe('fullscreen video sizing', () => {
  it('defaults to fitting the complete frame and rejects invalid stored choices', () => {
    localStorage.removeItem('peach.player.fullscreenSizing');
    expect(fullscreenSizing()).toBe('fit');
    localStorage.setItem('peach.player.fullscreenSizing', 'stretch');
    expect(fullscreenSizing()).toBe('fit');
  });
  it('applies original resolution without upscaling and synchronizes active players', () => {
    const first = document.createElement('div'), second = document.createElement('div');
    const stopFirst = mountFullscreenSizing(first), stopSecond = mountFullscreenSizing(second);
    try {
      setFullscreenSizing('original');
      expect(first.style.getPropertyValue('--peach-fullscreen-fit')).toBe('scale-down');
      expect(second.dataset.fullscreenSizing).toBe('original');
      expect(fullscreenSizing()).toBe('original');
      setFullscreenSizing('fill');
      expect(first.style.getPropertyValue('--peach-fullscreen-fit')).toBe('cover');
      setFullscreenSizing('fit');
      expect(second.style.getPropertyValue('--peach-fullscreen-fit')).toBe('contain');
    } finally { stopFirst(); stopSecond(); }
  });
  it('restores the selected mode for a new player and detaches disposed players', () => {
    setFullscreenSizing('original');
    const root = document.createElement('div');
    const stop = mountFullscreenSizing(root);
    expect(root.dataset.fullscreenSizing).toBe('original');
    stop();
    setFullscreenSizing('fit');
    expect(root.dataset.fullscreenSizing).toBe('original');
  });
});
