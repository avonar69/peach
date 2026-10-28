import { QueryClientProvider, notifyManager } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { NZBGetSettings, SABnzbdSettings } from '../../src/react/settings/sabnzbd-settings';
import { queryClient } from '../../src/react/query';
import { buttonNamed, click, mount, submit, type } from './render';

notifyManager.setScheduler(callback => callback());
beforeEach(() => localStorage.setItem('peach.language', 'en'));
afterEach(() => { queryClient.clear(); localStorage.clear(); });

it('NZBGet 保存用户名与隐藏的密码并验证连接', async () => {
  const posts: { path: string; body: Record<string, unknown> }[] = [];
  vi.stubGlobal('fetch', vi.fn(async (raw: string, options?: RequestInit) => {
    if (options?.method === 'POST') posts.push({ path: String(raw), body: JSON.parse(String(options.body)) });
    return { ok: true, status: 200, json: async () => options?.method === 'POST' ? { ok: true }
      : { url: 'http://nzbget:6789/jsonrpc', category: 'movies', username: 'demo', configured: true, available: true } };
  }));
  const host = await mount(<QueryClientProvider client={queryClient}><NZBGetSettings receipt={vi.fn()} /></QueryClientProvider>);
  const inputs = host.querySelectorAll('input');
  expect(inputs[2]?.type).toBe('password');
  expect(inputs[2]?.value).toBe('');
  await type(inputs[2]!, 'example-password');
  await submit(host.querySelector('form'));
  expect(posts[0]).toEqual({ path: '/api/configuration/nzbget/settings', body: {
    url: 'http://nzbget:6789/jsonrpc', username: 'demo', category: 'movies', password: 'example-password', remove_key: false,
  } });
  await click(buttonNamed('Test connection', host));
  expect(posts.at(-1)?.path).toBe('/api/configuration/nzbget/check');
  expect(host.textContent).toContain('NZBGet connection successful.');
});

it('本机下载配置保存空密钥、验证连接与撤销密钥', async () => {
  const posts: { path: string; body: Record<string, unknown> }[] = [];
  vi.stubGlobal('fetch', vi.fn(async (raw: string, options?: RequestInit) => {
    if (options?.method === 'POST') posts.push({ path: String(raw), body: JSON.parse(String(options.body)) });
    return { ok: true, status: 200, json: async () => options?.method === 'POST' ? { ok: true }
      : { url: 'http://sabnzbd:8080/api', category: 'movies', configured: true, available: true } };
  }));
  const host = await mount(<QueryClientProvider client={queryClient}><SABnzbdSettings receipt={vi.fn()} /></QueryClientProvider>);
  const form = host.querySelector('form');
  const inputs = host.querySelectorAll('input');
  expect(inputs[1]?.type).toBe('password');
  expect(inputs[1]?.value).toBe('');
  await type(inputs[2]!, 'videos');
  await submit(form);
  expect(posts[0]).toEqual({ path: '/api/configuration/sabnzbd/settings', body: {
    url: 'http://sabnzbd:8080/api', category: 'videos', api_key: '', remove_key: false,
  } });
  await click(buttonNamed('Test connection', host));
  expect(posts.at(-1)?.path).toBe('/api/configuration/sabnzbd/check');
  expect(host.textContent).toContain('SABnzbd connection successful.');
  await click(buttonNamed('Remove API key', host));
  expect(posts.at(-1)?.body.remove_key).toBe(true);
});
