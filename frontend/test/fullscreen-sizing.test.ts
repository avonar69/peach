import { afterEach, describe, expect, it, vi } from 'vitest';
import { fullscreenControl } from '../src/player/fullscreen';
import { fullscreenSizing, mountFullscreenSizing, setFullscreenSizing } from '../src/player/fullscreen-sizing';

afterEach(() => localStorage.removeItem('peach.player.fullscreenSizing'));
describe('fullscreen video sizing', () => {
  it('keeps an explicit control usable when native fullscreen is unavailable', async () => {
    const root = document.createElement('div');
    root.innerHTML = '<button class="vjs-fullscreen-control"></button><video></video>';
    const video = root.querySelector('video')!, button = root.querySelector('button')!;
    const request = vi.fn().mockRejectedValue(new Error('not available'));
    root.requestFullscreen = request;
    const stop = fullscreenControl(root, video, vi.fn());
    button.click(); await Promise.resolve(); await Promise.resolve();
    expect(button.hidden).toBe(false);
    expect(root.hasAttribute('data-peach-full-window')).toBe(true);
    button.click(); await Promise.resolve();
    expect(root.hasAttribute('data-peach-full-window')).toBe(false);
    stop();
  });
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
