/** 全屏画面尺寸按浏览器保存，多播放器共享同一选择。 */
export type FullscreenSizing = 'fit' | 'original' | 'fill';
const KEY = 'peach.player.fullscreenSizing';
const EVENT = 'peachfullscreensizingchange';
const modes: Readonly<Record<FullscreenSizing, string>> = { fit: 'contain', original: 'scale-down', fill: 'cover' };
export function fullscreenSizing(): FullscreenSizing {
  try {
    const value = localStorage.getItem(KEY);
    return value === 'original' || value === 'fill' ? value : 'fit';
  } catch { return 'fit'; }
}
export function setFullscreenSizing(value: FullscreenSizing): void {
  try { localStorage.setItem(KEY, value); } catch { /* 本轮播放仍可应用。 */ }
  document.dispatchEvent(new CustomEvent(EVENT, { detail: value }));
}
export function mountFullscreenSizing(root: HTMLElement): () => void {
  const apply = (mode: FullscreenSizing) => {
    root.dataset.fullscreenSizing = mode;
    root.style.setProperty('--peach-fullscreen-fit', modes[mode]);
  };
  apply(fullscreenSizing());
  const change = (event: Event) => apply((event as CustomEvent<FullscreenSizing>).detail);
  document.addEventListener(EVENT, change);
  return () => document.removeEventListener(EVENT, change);
}
