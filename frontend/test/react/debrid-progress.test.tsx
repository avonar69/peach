import { act } from 'react';
import { QueryClientProvider, notifyManager } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { queryClient } from '../../src/react/query';
import { DebridDownloadDock, type DebridJob } from '../../src/react/follow-manage/debrid-progress';
import { DebridSettings } from '../../src/react/settings/debrid-settings';
import { buttonNamed, click, mount } from './render';

const sonner = vi.hoisted(() => ({ custom: vi.fn(), dismiss: vi.fn() }));
vi.mock('sonner', () => ({ toast: sonner }));
notifyManager.setScheduler(callback => callback());
beforeEach(() => { localStorage.setItem('peach.language', 'en'); sonner.custom.mockClear(); sonner.dismiss.mockClear() });
afterEach(() => { queryClient.clear(); localStorage.clear() });

async function open(job: DebridJob, readOnly = false) {
  localStorage.setItem('peach.debrid-progress', JSON.stringify([job.id]));
  const posts: unknown[] = [];
  vi.stubGlobal('fetch', vi.fn(async (_path: string, init?: RequestInit) => {
    if (init?.method === 'POST') posts.push(JSON.parse(String(init.body)));
    return { ok: true, json: async () => ({ jobs: [job], providers: [], read_only: readOnly }) };
  }));
  await mount(<QueryClientProvider client={queryClient}><DebridDownloadDock /></QueryClientProvider>);
  return posts;
}

const job: DebridJob = { id: 'file-one', entry_id: 1, provider: 'alldebrid', kind: 'download', status: 'downloading',
  filename: 'Example video.mp4', bytes: 500, total: 1000 };

it('下载浮层复用后台任务通知栈并显示真实字节进度和取消入口', async () => {
  const posts = await open(job);
  expect(sonner.custom).toHaveBeenCalled();
  const [render, options] = sonner.custom.mock.calls.at(-1)!;
  expect(options).toMatchObject({ toasterId: 'processing', className: 'processing-task-toast', duration: Infinity });
  const host = await mount(<QueryClientProvider client={queryClient}>{render()}</QueryClientProvider>);
  const bar = host.querySelector('progress')!;
  expect(bar.value).toBe(500);
  expect(bar.max).toBe(1000);
  await click(buttonNamed('Cancel download', host));
  expect(posts).toContainEqual({ id: 'file-one' });
});

it('下载完成后等待定向导入时继续显示浮层，取消导入保留下载', async () => {
  await open({ ...job, status: 'complete', import_state: 'queued' });
  const [render, options] = sonner.custom.mock.calls.at(-1)!;
  expect(options.dismissible).toBe(false);
  const host = await mount(<QueryClientProvider client={queryClient}>{render()}</QueryClientProvider>);
  expect(host.textContent).toContain('Import queued');
  expect(buttonNamed('Cancel import', host)).not.toBeNull();
});

it('已完成任务关闭后清除本机浮层观察清单，只读端停用取消', async () => {
  await open({ ...job, status: 'complete' }, true);
  const [, options] = sonner.custom.mock.calls.at(-1)!;
  expect(options.duration).toBe(8000);
  await act(async () => options.onDismiss());
  expect(JSON.parse(localStorage.getItem('peach.debrid-progress')!)).toEqual([]);
});

it('下载渠道保存独立的完成后扫描导入选项', async () => {
  const posts: Record<string, unknown>[] = [];
  const providers = [{ id: 'alldebrid', label: 'AllDebrid', configured: true, hosts: [], download_folder: '/downloads', auto_import: false }];
  vi.stubGlobal('fetch', vi.fn(async (_path: string, init?: RequestInit) => {
    if (init?.method === 'POST') posts.push(JSON.parse(String(init.body)));
    return { ok: true, json: async () => ({ providers }) };
  }));
  const host = await mount(<QueryClientProvider client={queryClient}><DebridSettings receipt={vi.fn()} /></QueryClientProvider>);
  await click(host.querySelector('[aria-label="Automatic import for AllDebrid"]'));
  await click(buttonNamed('Save debrid settings', host));
  expect(posts[0].auto_import).toBe(true);
  expect(posts[0].download_folder).toBe('/downloads');
});
