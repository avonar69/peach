/** 播放器四向跳转与滚轮音量共用偏好，不捕获编辑框或菜单的按键。 */
export const SEEK_ACTIONS = ['bigForward', 'smallForward', 'bigRewind', 'smallRewind'] as const;
export type SeekAction = typeof SEEK_ACTIONS[number];
export type SeekConfig = Record<SeekAction, { seconds: number; shortcut: string }>;
export const SEEK_DEFAULTS: SeekConfig = {
  bigForward: { seconds: 60, shortcut: 'ArrowUp' }, smallForward: { seconds: 10, shortcut: 'ArrowRight' },
  bigRewind: { seconds: 60, shortcut: 'ArrowDown' }, smallRewind: { seconds: 10, shortcut: 'ArrowLeft' },
};
export function shortcutFromEvent(event: Pick<KeyboardEvent, 'key' | 'ctrlKey' | 'altKey' | 'shiftKey' | 'metaKey'>): string {
  if (['Control', 'Alt', 'Shift', 'Meta', 'Tab', 'Escape', 'Dead', 'Unidentified'].includes(event.key)) return '';
  return [event.ctrlKey && 'Ctrl', event.altKey && 'Alt', event.shiftKey && 'Shift', event.metaKey && 'Meta',
    event.key.length === 1 ? event.key.toLowerCase() : event.key].filter(Boolean).join('+');
}
export function validShortcut(value: unknown): value is string {
  if (typeof value !== 'string' || !/^(?:(?:Ctrl|Alt|Shift|Meta)\+)*(?:Arrow(?:Up|Down|Left|Right)|[a-z0-9]|F(?:[1-9]|1[0-2]))$/.test(value)) return false;
  const parts = value.split('+'), key = parts.pop()!, modifiers = new Set(parts);
  if (modifiers.size !== parts.length || (modifiers.size === 0 && ['k', 'm', 'f', 'i', 't'].includes(key))) return false;
  if ((modifiers.has('Ctrl') || modifiers.has('Meta')) && ['w', 'r', 'l', 'n', 't', 'q', 'p'].includes(key)) return false;
  return !(modifiers.has('Alt') && key === 'F4');
}
export function seekConfig(value: unknown, legacy = 10): SeekConfig {
  const raw = value && typeof value === 'object' ? value as Partial<SeekConfig> : {};
  const result = {} as SeekConfig;
  const used = new Set<string>();
  for (const action of SEEK_ACTIONS) {
    const item = raw[action], fallback = SEEK_DEFAULTS[action];
    const seconds = Number(item?.seconds ?? (action.startsWith('small') ? legacy : fallback.seconds));
    const shortcut = validShortcut(item?.shortcut) && !used.has(item.shortcut) ? item.shortcut : fallback.shortcut;
    result[action] = { seconds: Number.isInteger(seconds) && seconds >= 1 && seconds <= 3600 ? seconds : fallback.seconds, shortcut };
    used.add(shortcut);
  }
  // 无效或重复的存量按键整体恢复默认，确保四个动作都可触发。
  if (new Set(Object.values(result).map(item => item.shortcut)).size !== 4)
    for (const action of SEEK_ACTIONS) result[action].shortcut = SEEK_DEFAULTS[action].shortcut;
  return result;
}
export function seekDelta(event: KeyboardEvent, value: unknown, legacy = 10): number | null {
  const key = shortcutFromEvent(event), config = seekConfig(value, legacy);
  const action = SEEK_ACTIONS.find(action => config[action].shortcut === key);
  return action ? config[action].seconds * (action.endsWith('Rewind') ? -1 : 1) : null;
}
export function wheelVolume(root: HTMLElement, video: HTMLVideoElement, enabled: () => boolean): () => void {
  const wheel = (event: WheelEvent) => {
    const target = event.target as Element | null;
    if (!enabled() || event.ctrlKey || !event.deltaY || Math.abs(event.deltaX) > Math.abs(event.deltaY)
      || target?.closest('.vjs-control-bar,.vjs-peach-panel,[role="menu"],input,textarea,select')) return;
    event.preventDefault();
    video.volume = Math.max(0, Math.min(1, video.volume + (event.deltaY < 0 ? .05 : -.05)));
    if (video.volume > 0) video.muted = false;
  };
  root.addEventListener('wheel', wheel, { passive: false });
  return () => root.removeEventListener('wheel', wheel);
}
