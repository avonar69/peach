import { QueryClientProvider, notifyManager } from '@tanstack/react-query';
import { afterEach, expect, it, vi } from 'vitest';
import { queryClient } from '../../src/react/query';
import { TranscodeCacheSettings } from '../../src/react/settings/transcode-cache-settings';
import { buttonNamed, click, mount, type } from './render';

notifyManager.setScheduler(callback => callback());
afterEach(() => { queryClient.clear(); localStorage.clear() });

it('保存服务端目录与总容量，并显示目录重启提示', async () => {
  localStorage.setItem('peach.language', 'en');
  const posts: unknown[] = [];
  const value = { folder: '', max_gb: 10, used_bytes: 1024, active_folder: '/cache', restart_required: false };
  vi.stubGlobal('fetch', vi.fn(async (_url: string, init?: RequestInit) => {
    if (init?.method === 'POST') { const body = JSON.parse(String(init.body)); posts.push(body); Object.assign(value, body, { restart_required: true }) }
    return { ok: true, json: async () => ({ ...value }) };
  }));
  const host = await mount(<QueryClientProvider client={queryClient}><TranscodeCacheSettings /></QueryClientProvider>);
  await type(host.querySelector('input[aria-label="Transcode folder"]'), '/downloads/cache');
  await type(host.querySelector('input[aria-label="Maximum transcode storage (GiB)"]'), '20');
  await click(buttonNamed('Save transcode storage', host));
  expect(posts).toEqual([{ folder: '/downloads/cache', max_gb: 20 }]);
  expect(host.textContent).toContain('Restart Peach');
});
