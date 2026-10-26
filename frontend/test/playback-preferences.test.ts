import { afterEach, describe, expect, it, vi } from 'vitest';
import { configuredSeekKeys, rememberVolume, seekConfig, seekDelta, shortcutFromEvent, validShortcut, wheelVolume } from '../src/player/playback-preferences';
import { navigationFreshness, performancePreferences } from '../src/performance-preferences';
import { queryClient } from '../src/query/client';

afterEach(() => { localStorage.clear(); queryClient.clear(); document.body.replaceChildren() });

describe('independent playback preferences', () => {
  it('restores volume and mute across videos without saving disposal changes', () => {
    const first = document.createElement('video');
    const release = rememberVolume(first);
    first.volume = .37; first.muted = true; first.dispatchEvent(new Event('volumechange'));
    release(); first.volume = 1; first.dispatchEvent(new Event('volumechange'));
    const second = document.createElement('video'), stop = rememberVolume(second);
    expect(second.volume).toBeCloseTo(.37); expect(second.muted).toBe(true); stop();
  });
  it('uses configured amounts before timeline controls can apply their default jump', () => {
    const root = document.createElement('div'), video = document.createElement('video');
    const slider = document.createElement('media-time-slider'); root.append(video, slider); document.body.append(root);
    const config = seekConfig(undefined); config.bigForward.seconds = 90; config.smallForward.seconds = 23;
    const fallback = vi.fn(); slider.addEventListener('keydown', fallback, true);
    const stop = configuredSeekKeys(root, video, () => ({ playerSeek: config, seekSeconds: 10 }));
    video.currentTime = 100;
    slider.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true, cancelable: true }));
    expect(video.currentTime).toBe(190); expect(fallback).not.toHaveBeenCalled();
    config.smallForward.seconds = 31;
    slider.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true, cancelable: true }));
    expect(video.currentTime).toBe(221);
    const input = document.createElement('input'); root.append(input);
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
    expect(video.currentTime).toBe(221); stop();
  });
  it('keeps beta options off by default and reuses only browsing snapshots when enabled', async () => {
    expect(performancePreferences()).toEqual({ video: false, ui: false });
    expect(navigationFreshness(['stats'])).toBe(0);
    localStorage.setItem('peach.settings.v1', JSON.stringify({ betaFastUI: true, betaFastVideo: true }));
    expect(performancePreferences()).toEqual({ video: true, ui: true });
    expect(navigationFreshness(['stats'])).toBe(30_000);
    expect(navigationFreshness(['review', 'counts'])).toBe(0);
    expect(navigationFreshness(['tasks'])).toBe(0);
    const load = vi.fn(async () => ({ count: 1 }));
    await queryClient.fetchQuery({ queryKey: ['stats'], queryFn: load });
    await queryClient.fetchQuery({ queryKey: ['stats'], queryFn: load });
    expect(load).toHaveBeenCalledOnce();
    await queryClient.invalidateQueries({ queryKey: ['stats'] });
    await queryClient.fetchQuery({ queryKey: ['stats'], queryFn: load });
    expect(load).toHaveBeenCalledTimes(2);
  });
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
