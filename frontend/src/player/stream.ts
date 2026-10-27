/* 流会话与片源判据。
 *
 * 每一路播放带一个会话号，服务端按它登记在途的读取；切走、关闭、离开页面时按会话取消，
 * 已经没人看的读取不再占着 115 或本地盘。详情与沉浸模式共用这一套（沉浸模式每格一个会话）。 */
import { api } from '@peach/legacy/core';
import { performancePreferences } from '../performance-preferences';
import { browserSupportsMedia, nativeAv1Supported, type MediaProbe } from '../media-capabilities';
import { cancelStreamSession, newStreamSession } from '../media-sessions';
export { cancelStreamSession, newStreamSession } from '../media-sessions';

import type { PlaybackInfo, PlayerItem, PlayerSource } from './types';

export function directStreamSource(item: PlayerItem, session: string, nativePlay?: boolean): PlayerSource {
  return {
    src: localBuffering(`/stream?id=${item.id}&session=${encodeURIComponent(session)}${nativePlay !== undefined ? `&native_play=${nativePlay}` : nativeAv1Supported() ? '&native_av1=true' : ''}`, item),
    type: nativePlay === false ? 'video/mp4' : String(item.name || '').toLowerCase().endsWith('.webm') ? 'video/webm' : 'video/mp4',
  };
}

function localBuffering(src: string, item: PlayerItem): string {
  return performancePreferences().video && item.location === 'local' && item.cost !== 'metered' && src.startsWith('/stream?')
    ? `${src}&beta_fast=1` : src;
}

/* 在线作品的 `path` 是来源作品页，不是可播地址。能播的那条代理在 `/follow-stream?id=<follow_item>`，
   保存时写了 `follow_item.asset_id`，`/api/item` 反查后回传 `follow_item_id`。 */
function followStreamSource(item: PlayerItem): PlayerSource | null {
  return item.location === 'online' && item.follow_item_id
    ? { src: `/follow-stream?id=${item.follow_item_id}`, type: 'video/mp4' } : null;
}

/** 起播片源只有这一个判据，详情和沉浸模式共用：服务端说要转码分片就给分片，否则直读。
 *  有 B 帧却缺 ctts 的 MP4 直读时浏览器按错的显示顺序丢帧，整片持续卡顿。 */
export async function playableStreamSource(item: PlayerItem, session: string, forceConversion = false): Promise<PlayerSource> {
  const proxied = followStreamSource(item);
  if (proxied) return proxied;
  try {
    const base = `/api/stream-plan?id=${item.id}&session=${encodeURIComponent(session)}`;
    const inspection = !forceConversion ? await api(`${base}&probe_only=true${nativeAv1Supported() ? '&native_av1=true' : ''}`) as
      { probe?: MediaProbe; protocol?: string; src?: string; mime_type?: string; playback?: PlaybackInfo } | null : null;
    const native = inspection?.probe ? await browserSupportsMedia(inspection.probe) : undefined;
    const plan = inspection?.src ? inspection : await api(`${base}${forceConversion ? '&native_play=false' : native !== undefined ? `&native_play=${native}` : nativeAv1Supported() ? '&native_av1=true' : ''}`) as
      { protocol?: string; src?: string; mime_type?: string; playback?: PlaybackInfo } | null;
    if (plan?.src) return { src: localBuffering(plan.src, item), type: plan.mime_type || (plan.protocol === 'hls' ? 'application/vnd.apple.mpegurl' : 'video/mp4'),
      ...(plan.playback ? { playback: forceConversion ? { ...plan.playback, reason: 'Direct playback failed; using compatibility conversion' } : plan.playback } : {}) };
  } catch { /* 取不到计划就直读 */ }
  return directStreamSource(item, session);
}

/* ── 详情这一路 ──
   舞台与小窗同一时刻只放一条，共用一个会话：从详情进小窗时读取接着用，小窗里换片或关掉时
   才取消。 */
let detailSession = '';

export function detailStreamSession(): string { return detailSession }

function ensureDetailSession(): string {
  if (!detailSession) detailSession = newStreamSession();
  return detailSession;
}

export const directDetailSource = (item: PlayerItem, forceConversion = false): PlayerSource => directStreamSource(item, ensureDetailSession(), forceConversion ? false : undefined);
export const detailStreamSource = (item: PlayerItem, forceConversion = false): Promise<PlayerSource> => playableStreamSource(item, ensureDetailSession(), forceConversion);

export function cancelDetailStream(): void {
  const session = detailSession;
  if (!session) return;
  detailSession = '';
  cancelStreamSession(session);
}
