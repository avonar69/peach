import { QueryClientProvider, notifyManager } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { RSSDownloads, supports } from '../../src/react/follow-manage/rss-downloads';
import { queryClient } from '../../src/react/query';
import { buttonNamed, click, mount } from './render';

notifyManager.setScheduler(callback => callback());
beforeEach(() => localStorage.setItem('peach.language', 'en'));
afterEach(() => { queryClient.clear(); localStorage.clear(); });

const provider = { id: 'alldebrid', label: 'AllDebrid', configured: true, hosts: ['rg.to'], download_folder: '' };
const link = { url: 'https://rg.to/file/example', kind: 'link' };

function serve(folder = '') {
  const posts: Array<{ path: string; body: Record<string, unknown> }> = [];
  const state = { providers: [{ ...provider, download_folder: folder }], sources: [],
    items: [{ id: 1, title: 'Example video', feed_name: 'Example feed', published_at: null, links: [link] }],
    jobs: [] as Array<Record<string, unknown>>, total: 1, offset: 0 };
  vi.stubGlobal('fetch', vi.fn(async (raw: string, options?: RequestInit) => {
    const path = String(raw);
    if (options?.method === 'POST') {
      const body = JSON.parse(String(options.body || '{}'));
      posts.push({ path, body });
      if (path.endsWith('/resolve')) state.jobs = [{ id: 'prepared', entry_id: 1, provider: 'alldebrid',
        source: link, kind: 'resolve', status: 'ready', files: [{ url: 'https://cdn.example.org/video', filename: 'video.mp4' }] }];
      return { ok: true, status: 200, json: async () => ({ id: 'prepared' }) };
    }
    return { ok: true, status: 200, json: async () => state };
  }));
  return { posts, state };
}

it('RSS 原始链接旁的一次点击准备链接并开始浏览器下载', async () => {
  const served = serve(), download = vi.fn();
  const host = await mount(<QueryClientProvider client={queryClient}>
    <RSSDownloads readOnly={false} toast={vi.fn()} download={download} />
  </QueryClientProvider>);
  const icon = host.querySelector<HTMLButtonElement>('button[aria-label="Download with AllDebrid"]');
  expect(icon).not.toBeNull();
  expect(icon?.parentElement?.querySelector('a')?.href).toBe(link.url);
  await click(icon);
  expect(served.posts[0]).toEqual({ path: '/api/rss/resolve', body: { entry_id: 1, link_index: 0, provider: 'alldebrid' } });
  expect(download).toHaveBeenCalledWith('https://cdn.example.org/video');
});

it('配置目录后同一枚图标提交目录下载', async () => {
  const served = serve('/downloads'), download = vi.fn();
  const host = await mount(<QueryClientProvider client={queryClient}>
    <RSSDownloads readOnly={false} toast={vi.fn()} download={download} />
  </QueryClientProvider>);
  await click(host.querySelector('button[aria-label="Download with AllDebrid"]'));
  expect(served.posts).toContainEqual({ path: '/api/rss/download', body: { id: 'prepared', file_index: 0 } });
  expect(download).not.toHaveBeenCalled();
});

it('只读端保留原始链接并停用下载图标', async () => {
  const served = serve();
  const host = await mount(<QueryClientProvider client={queryClient}>
    <RSSDownloads readOnly toast={vi.fn()} />
  </QueryClientProvider>);
  expect(host.querySelector<HTMLButtonElement>('button[aria-label="Download with AllDebrid"]')?.disabled).toBe(true);
  expect(buttonNamed('Add RSS feed', host)?.disabled).toBe(true);
  expect(served.posts).toEqual([]);
});

it('支持域名按主机边界匹配，磁力复用同一枚图标', () => {
  expect(supports(provider, link)).toBe(true);
  expect(supports(provider, { ...link, url: 'https://evilrg.to/file' })).toBe(false);
  expect(supports(provider, { ...link, url: 'https://sub.rg.to/file' })).toBe(true);
  expect(supports({ ...provider, configured: false }, link)).toBe(false);
  expect(supports(provider, { url: 'magnet:?xt=urn:btih:test', kind: 'magnet' })).toBe(true);
});
