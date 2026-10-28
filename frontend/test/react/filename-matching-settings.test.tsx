import { expect, it, vi } from 'vitest';
import { act } from 'react';
import { FilenameMatchingSettings } from '../../src/react/settings/filename-matching-settings';
import { buttonNamed, click, mount, pending, settle } from './render';

it('保存忽略词后只启动文件名重匹配阶段', async () => {
  localStorage.setItem('peach.language', 'en');
  const calls: { path: string; body: unknown }[] = [];
  vi.stubGlobal('fetch', vi.fn(async (path: string, init?: RequestInit) => {
    const body = JSON.parse(String(init?.body)); calls.push({ path, body });
    return { ok: true, status: 200, json: async () => path.endsWith('filename-matching') ? body : { requested_stage: 'filename_ignored' } };
  }));
  const host = await mount(<FilenameMatchingSettings initial={{ actors: true, studios: true }} receipt={vi.fn()} />);
  await act(async () => {
    const textarea = host.querySelector('textarea')!;
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')!.set!.call(textarea, '!');
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await click(buttonNamed('Rematch affected filenames', host));
  expect(calls.map(call => call.path)).toEqual(['/api/configuration/filename-matching', '/api/library-processing']);
  expect(calls[0]?.body).toEqual({ actors: true, studios: true, ignore_terms: '!' });
  expect(calls[1]?.body).toEqual({ stage: 'filename_ignored' });
  localStorage.removeItem('peach.language');
});

it('saves independent actor and studio switches after server confirmation', async () => {
  const saved = pending<{ actors: boolean; studios: boolean }>();
  const receipt = vi.fn();
  const requests: unknown[] = [];
  vi.stubGlobal('fetch', vi.fn(async (_url: string, init?: RequestInit) => {
    requests.push(JSON.parse(String(init?.body)));
    return { ok: true, json: () => saved.answer };
  }));
  const host = await mount(<FilenameMatchingSettings initial={{ actors: false, studios: false }} receipt={receipt} />);
  const controls = host.querySelectorAll<HTMLInputElement>('input[type="checkbox"]');
  await click(controls[1]);
  await settle();
  expect(requests).toEqual([{ actors: false, studios: true }]);
  expect(receipt).not.toHaveBeenCalled();
  await saved.release({ actors: false, studios: true });
  await settle();
  expect(controls[0]?.checked).toBe(false);
  expect(controls[1]?.checked).toBe(true);
  expect(receipt).toHaveBeenCalledWith('已保存文件名匹配设置');
});

it('keeps the saved policy and shows the error when a change fails', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 400, json: async () => ({ detail: '保存失败' }) })));
  const receipt = vi.fn();
  const host = await mount(<FilenameMatchingSettings initial={{ actors: true, studios: false }} receipt={receipt} />);
  await click(host.querySelector<HTMLInputElement>('input[type="checkbox"]'));
  await settle();
  expect(host.querySelector<HTMLInputElement>('input[type="checkbox"]')?.checked).toBe(true);
  expect(receipt).not.toHaveBeenCalled();
  expect(host.textContent).toContain('保存失败');
});
