/** 触屏同侧双击使用小步长；单击延后兑现，滑动与多点触控不接管。 */
import { seekVideoBy, toggleVideoPlayback } from './playback';
import { seekConfig, type SeekConfig } from './playback-preferences';

export function touchSeek(video: HTMLVideoElement, settings: () => { playerSeek?: SeekConfig; seekSeconds: number }): () => void {
  let down: { id: number; x: number; y: number; at: number } | null = null;
  let tap: { side: number; at: number } | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let ignoreUntil = 0;
  const clear = () => { clearTimeout(timer); timer = undefined; tap = null };
  const start = (event: PointerEvent) => {
    if (event.pointerType !== 'touch') return;
    if (!event.isPrimary) { down = null; clear(); return }
    down = { id: event.pointerId, x: event.clientX, y: event.clientY, at: Date.now() };
  };
  const finish = (event: PointerEvent) => {
    if (!down || event.pointerId !== down.id) return;
    const held = down; down = null;
    if (Date.now() - held.at > 500 || Math.hypot(event.clientX - held.x, event.clientY - held.y) > 20) { clear(); return }
    event.preventDefault(); ignoreUntil = Date.now() + 700;
    const rect = video.getBoundingClientRect(), side = event.clientX < rect.left + rect.width / 2 ? -1 : 1;
    if (tap && tap.side === side && Date.now() - tap.at <= 300) {
      clear();
      const saved = settings(), config = seekConfig(saved.playerSeek, saved.seekSeconds);
      seekVideoBy(video, side * config[side > 0 ? 'smallForward' : 'smallRewind'].seconds);
      return;
    }
    if (tap) { clear(); toggleVideoPlayback(video) }
    tap = { side, at: Date.now() };
    timer = setTimeout(() => { clear(); toggleVideoPlayback(video) }, 300);
  };
  const suppress = (event: Event) => { if (Date.now() < ignoreUntil) { event.preventDefault(); event.stopImmediatePropagation() } };
  const cancel = () => { down = null; clear() };
  video.addEventListener('pointerdown', start);
  video.addEventListener('pointerup', finish);
  video.addEventListener('pointercancel', cancel);
  video.addEventListener('click', suppress, true);
  video.addEventListener('dblclick', suppress, true);
  return () => {
    cancel(); video.removeEventListener('pointerdown', start); video.removeEventListener('pointerup', finish);
    video.removeEventListener('pointercancel', cancel); video.removeEventListener('click', suppress, true);
    video.removeEventListener('dblclick', suppress, true);
  };
}
