import { QueryClientProvider, notifyManager } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { queryClient } from '../../src/react/query';
import { ThumbnailGenerationCard, ThumbnailGenerationNotice } from '../../src/react/library-processing/thumbnail-generation-notice';
import { buttonNamed, click, mount } from './render';

const sonner = vi.hoisted(() => ({ custom: vi.fn(), dismiss: vi.fn() }));
vi.mock('sonner', () => ({ toast: sonner }));
notifyManager.setScheduler(callback => callback());
beforeEach(() => { localStorage.setItem('peach.language', 'en'); sonner.custom.mockClear(); sonner.dismiss.mockClear() });
afterEach(() => { queryClient.clear(); localStorage.clear() });

it('独立缩略图工作者显示逐帧进度并允许停止', async () => {
  const posts: unknown[] = [];
  vi.stubGlobal('fetch', vi.fn(async (_path: string, init?: RequestInit) => {
    if (init?.method === 'POST') posts.push(JSON.parse(String(init.body)));
    return { ok: true, json: async () => ({ status: posts.length ? 'idle' : 'running', done: 2, total: 10, current_frame: 55, current_frames: 100 }) };
  }));
  await mount(<QueryClientProvider client={queryClient}><ThumbnailGenerationNotice /></QueryClientProvider>);
  const [render, options] = sonner.custom.mock.calls.at(-1)!;
  expect(options).toMatchObject({ toasterId: 'processing', duration: Infinity, dismissible: false });
  const host = await mount(<QueryClientProvider client={queryClient}>{render()}</QueryClientProvider>);
  expect(host.textContent).toContain('55 of 100 frames');
  expect(host.querySelector('progress')?.value).toBe(2);
  await click(buttonNamed('Stop thumbnail generation', host));
  expect(posts).toEqual([{ mode: 'off' }]);
  expect(sonner.dismiss).toHaveBeenCalledWith('peach-timeline-generation');
});

it('空闲工作者关闭通知', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ status: 'idle' }) })));
  await mount(<QueryClientProvider client={queryClient}><ThumbnailGenerationNotice /></QueryClientProvider>);
  expect(sonner.custom).not.toHaveBeenCalled();
  expect(sonner.dismiss).toHaveBeenCalledWith('peach-timeline-generation');
});

it('数据管理使用同一工作者快照并停止采集', async () => {
  const posts: unknown[] = [];
  vi.stubGlobal('fetch', vi.fn(async (_path: string, init?: RequestInit) => {
    if (init?.method === 'POST') posts.push(JSON.parse(String(init.body)));
    return { ok: true, json: async () => ({ status: posts.length ? 'idle' : 'running', done: 3, total: 12, current_frame: 8, current_frames: 100 }) };
  }));
  const host = await mount(<QueryClientProvider client={queryClient}><ThumbnailGenerationCard /></QueryClientProvider>);
  expect(host.textContent).toContain('3 of 12 videos');
  expect(host.textContent).toContain('8 of 100 frames');
  await click(buttonNamed('Stop thumbnail generation', host));
  expect(posts).toEqual([{ mode: 'off' }]);
  expect(host.textContent).toBe('');
});
