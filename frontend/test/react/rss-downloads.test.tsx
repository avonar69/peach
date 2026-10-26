import { QueryClientProvider, notifyManager } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { RSSDownloads, supports } from '../../src/react/follow-manage/rss-downloads';
import { queryClient } from '../../src/react/query';
import { buttonNamed, click, mount, type, submit } from './render';

notifyManager.setScheduler(callback => callback());
beforeEach(() => localStorage.setItem('peach.language', 'en'));
afterEach(() => { queryClient.clear(); localStorage.clear(); });

const provider = { id: 'alldebrid', label: 'AllDebrid', configured: true, hosts: ['rg.to'], download_folder: '' };
const link = { url: 'https://rg.to/file/example', kind: 'link' };

function serve(folder = '') {
  const posts: Array<{ path: string; body: Record<string, unknown> }> = [];
  const state = { providers: [{ ...provider, download_folder: folder }],
    sources: [{ id: 1, name: 'Example feed', enabled: true, interval_minutes: 360, hide_unsupported: false,
      rss_retention_count: null as number | null, rss_retention_unit: 'days' }],
    items: [{ id: 1, source_id: 1, title: 'Example video', feed_name: 'Example feed', published_at: null, links: [link],
      images: {} as { main?: { src: string; href: string }; previews?: Array<{ src: string; href: string }> } }],
    jobs: [] as Array<Record<string, unknown>>, total: 1, offset: 0 };
  vi.stubGlobal('fetch', vi.fn(async (raw: string, options?: RequestInit) => {
    const path = String(raw);
    if (options?.method === 'POST') {
      const body = JSON.parse(String(options.body || '{}'));
      posts.push({ path, body });
      if (body.action === 'schedule') Object.assign(state.sources[0], { enabled: body.enabled, interval_minutes: body.interval_minutes });
      if (body.action === 'retention') Object.assign(state.sources[0], { rss_retention_count: body.count, rss_retention_unit: body.unit });
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
  expect(served.posts[0]).toEqual({ path: '/api/rss/resolve', body: { entry_id: 1, link_index: 0, provider: 'alldebrid', auto_download: false } });
  expect(download).toHaveBeenCalledWith('https://cdn.example.org/video');
});

it('配置目录后同一枚图标提交目录下载', async () => {
  const served = serve('/downloads'), download = vi.fn();
  const host = await mount(<QueryClientProvider client={queryClient}>
    <RSSDownloads readOnly={false} toast={vi.fn()} download={download} />
  </QueryClientProvider>);
  await click(host.querySelector('button[aria-label="Download with AllDebrid"]'));
  expect(served.posts).toContainEqual({ path: '/api/rss/resolve', body: { entry_id: 1, link_index: 0, provider: 'alldebrid', auto_download: true } });
  expect(served.posts.filter(post => post.path === '/api/rss/download')).toHaveLength(0);
  expect(download).not.toHaveBeenCalled();
});

it('RSS 默认每页二十条，下一页请求独立偏移', async () => {
  const served = serve();
  served.state.total = 45;
  const host = await mount(<QueryClientProvider client={queryClient}><RSSDownloads readOnly={false} toast={vi.fn()} /></QueryClientProvider>);
  expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes('offset=0&limit=20'))).toBe(true);
  await click(buttonNamed('Next', host));
  expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes('offset=20&limit=20'))).toBe(true);
});

it('已完成文件显示完成状态并保留原始链接', async () => {
  const served = serve('/downloads');
  served.state.jobs = [{ id: 'prepared', entry_id: 1, provider: 'alldebrid', kind: 'resolve', status: 'ready',
    files: [{ filename: 'video.mp4', url: 'https://cdn.example.org/video', download_id: 'downloaded' }] },
  { id: 'downloaded', entry_id: 1, provider: 'alldebrid', kind: 'download', status: 'complete', parent_id: 'prepared', file_index: 0 }];
  const host = await mount(<QueryClientProvider client={queryClient}><RSSDownloads readOnly={false} toast={vi.fn()} /></QueryClientProvider>);
  expect(host.textContent).toContain('Download complete');
  expect(buttonNamed('Download file', host)).toBeNull();
  expect(host.querySelector('a[href="https://cdn.example.org/video"]')).not.toBeNull();
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
  expect(supports({ ...provider, hosts: [] }, link, true)).toBe(false);
});

it('每个 RSS 来源默认六小时并保存独立的自动更新间隔', async () => {
  const { posts } = serve();
  const host = await mount(<QueryClientProvider client={queryClient}><RSSDownloads readOnly={false} toast={vi.fn()} /></QueryClientProvider>);
  const interval = host.querySelector<HTMLInputElement>('[aria-label="Update interval for Example feed (hours)"]')!;
  expect(interval.value).toBe('6');
  await type(interval, '2');
  await submit(interval.closest('form'));
  expect(posts).toContainEqual({ path: '/api/rss/source', body: { action: 'schedule', id: 1, enabled: true, interval_minutes: 120 } });
  await click(host.querySelector('[aria-label="Enable Example feed"]'));
  expect(posts).toContainEqual({ path: '/api/rss/source', body: { action: 'schedule', id: 1, enabled: false, interval_minutes: 120 } });
});

it('关注页使用同一组 RSS 图片与下载入口而不显示订阅设置', async () => {
  serve();
  const host = await mount(<QueryClientProvider client={queryClient}><RSSDownloads feedOnly readOnly={false} toast={vi.fn()} /></QueryClientProvider>);
  expect(host.textContent).toContain('RSS updates');
  expect(host.querySelector('article')?.textContent).toContain('Example video');
  expect(host.querySelector('a[href="https://rg.to/file/example"]')).not.toBeNull();
  expect(host.querySelector('button[aria-label="Download with AllDebrid"]')).not.toBeNull();
  expect(host.querySelector('form')).toBeNull();
});

it('RSS 保存期限默认永久，按来源保存月份与数量', async () => {
  const { posts } = serve();
  const host = await mount(<QueryClientProvider client={queryClient}><RSSDownloads readOnly={false} toast={vi.fn()} /></QueryClientProvider>);
  const form = [...host.querySelectorAll('form')].find(item => item.textContent?.includes('Save retention'))!;
  expect(form.textContent).toContain('Forever');
  await click(form.querySelector('button[aria-haspopup="listbox"]'));
  await click([...document.querySelectorAll('[role="option"]')].find(item => item.textContent?.trim() === 'Months'));
  const amount = form.querySelector<HTMLInputElement>('[aria-label="Retention amount for Example feed"]');
  await type(amount, '6');
  await submit(form);
  expect(posts).toContainEqual({ path: '/api/rss/source', body: { action: 'retention', id: 1, count: 6, unit: 'months' } });
});

it('图文条目显示主图和全部预览缩略图并保留各自原图链接', async () => {
  const { state } = serve();
  state.items[0].images = { main: { src: 'https://images.example.org/main.webp', href: 'https://images.example.org/main' },
    previews: [{ src: 'https://images.example.org/preview.webp', href: 'https://images.example.org/full' },
      { src: 'https://images.example.org/preview2.webp', href: 'https://images.example.org/full2' }] };
  const host = await mount(<QueryClientProvider client={queryClient}><RSSDownloads readOnly={false} toast={vi.fn()} /></QueryClientProvider>);
  const images = host.querySelectorAll('article img');
  expect(images.length).toBe(3);
  expect(images[1].closest('a')?.href).toBe('https://images.example.org/full');
  expect(images[2].closest('a')?.href).toBe('https://images.example.org/full2');
  expect(images[0].getAttribute('referrerpolicy')).toBe('no-referrer');
  expect(images[0].getAttribute('loading')).toBe('lazy');
});

it('来源过滤隐藏不支持的地址并保留原始下载序号', async () => {
  const { state, posts } = serve();
  state.sources[0].hide_unsupported = true;
  state.items[0].links = [{ url: 'https://unsupported.example.org/page', kind: 'link' }, link];
  const host = await mount(<QueryClientProvider client={queryClient}><RSSDownloads readOnly={false} toast={vi.fn()} download={vi.fn()} /></QueryClientProvider>);
  expect(host.querySelector('a[href="https://unsupported.example.org/page"]')).toBeNull();
  await click(host.querySelector('button[aria-label="Download with AllDebrid"]'));
  expect(posts[0].body.link_index).toBe(1);
  await click(host.querySelector('[role="switch"][aria-label="Hide unsupported links for Example feed"]'));
  expect(posts).toContainEqual({ path: '/api/rss/source', body: { action: 'filter', id: 1, hide_unsupported: false } });
});
