/* 播放快捷键与沉浸模式手势共用的两步：切换播放、快进快退。
 *
 * 直接操作原生元素而不是 Video.js 实例：舞台、小窗与沉浸模式的 Video.js 读的都是这个元素，沉浸
 * 模式在播放器脚本拉不到时还是裸 video，一条实现全盖住。读者是壳的键盘（`Application` 的
 * `activeVideo()` 取到的那一个）与沉浸岛的单击、双击。 */
import { fmtClock } from '@peach/legacy/core';
import { translate } from '../i18n';

const seekIndicators = new WeakMap<Element, { node: HTMLElement; timer: ReturnType<typeof setTimeout> }>();

/** 全屏快进反馈展示目标位置，连续按键复用同一浮层并延长可见时间。 */
function showFullscreenSeek(video: HTMLVideoElement): void {
  const host = document.fullscreenElement;
  if (!host || host === video || !host.contains(video) || !Number.isFinite(video.duration) || video.duration <= 0) return;
  const previous = seekIndicators.get(host);
  if (previous) clearTimeout(previous.timer);
  const node = previous?.node || document.createElement('div');
  node.className = 'peach-fullscreen-seek';
  node.dataset.fullscreenSeek = '';
  node.setAttribute('role', 'status');
  if (!node.isConnected) {
    node.append(document.createElement('span'), document.createElement('progress'));
    host.append(node);
  }
  node.querySelector('span')!.textContent = `${fmtClock(video.currentTime)} / ${fmtClock(video.duration)}`;
  const progress = node.querySelector('progress')!;
  progress.max = video.duration; progress.value = video.currentTime;
  progress.setAttribute('aria-label', translate('Playback position'));
  progress.setAttribute('aria-valuemin', '0'); progress.setAttribute('aria-valuemax', String(video.duration));
  progress.setAttribute('aria-valuenow', String(video.currentTime));
  const timer = setTimeout(() => { node.remove(); seekIndicators.delete(host) }, 1600);
  seekIndicators.set(host, { node, timer });
}

export function toggleVideoPlayback(video: HTMLVideoElement | null | undefined): void {
  if (!video) return;
  if (video.paused) video.play()?.catch(() => {}); else video.pause();
}

/** 快进快退若干秒，夹在 0 与总长之间。 */
export function seekVideoBy(video: HTMLVideoElement, seconds: number): void {
  const total = video.duration;
  const target = (video.currentTime || 0) + seconds;
  // duration 在元数据到位前是 NaN，此时只夹下界，不要拿 NaN 去比上界。
  video.currentTime = Number.isFinite(total) ? Math.max(0, Math.min(total, target)) : Math.max(0, target);
  showFullscreenSeek(video);
}
