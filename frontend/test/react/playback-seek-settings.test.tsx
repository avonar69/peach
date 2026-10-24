import { act } from 'react';
import { expect, it, vi } from 'vitest';
import { PlaybackSeekSettings } from '../../src/react/settings-panel/playback-seek-settings';
import type { PanelSettings } from '../../src/react/settings-panel/settings-panel-api';
import { click, mount, type } from './render';

it('saves different amounts and captures custom shortcuts while refusing duplicates', async () => {
  const settings = { seekSeconds: 10 } as PanelSettings, save = vi.fn();
  const host = await mount(<PlaybackSeekSettings settings={settings} save={save} />);
  const amount = host.querySelector<HTMLInputElement>('[data-seek-action="bigForward"] input[type="number"]')!;
  await type(amount, '123');
  await act(async () => { amount.dispatchEvent(new FocusEvent('focusout', { bubbles: true })); });
  expect(settings.playerSeek?.bigForward.seconds).toBe(123);
  const shortcut = host.querySelector<HTMLInputElement>('[data-seek-action="bigForward"] input[readonly]')!;
  await act(async () => { shortcut.dispatchEvent(new KeyboardEvent('keydown', { key: 'g', shiftKey: true, bubbles: true })); });
  expect(settings.playerSeek?.bigForward.shortcut).toBe('Shift+g');
  const called = save.mock.calls.length;
  await act(async () => { shortcut.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true })); });
  expect(save.mock.calls.length).toBe(called);
  expect(host.querySelector('[role="alert"]')?.textContent).toBeTruthy();
  expect(settings.playerSeek?.smallRewind.shortcut).toBe('ArrowLeft');
  await click(host.querySelector('button'));
  expect(settings.playerSeek?.bigForward.seconds).toBe(123);
  expect(settings.playerSeek?.bigForward.shortcut).toBe('ArrowUp');
  expect(host.querySelector<HTMLInputElement>('[data-seek-action="bigForward"] input[type="number"]')?.value).toBe('123');
});
