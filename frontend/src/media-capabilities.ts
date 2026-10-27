/** 仅在客户端报告支持 8/10-bit AV1 MP4 时请求原片；实际失败仍可回退。 */
import { api } from '@peach/legacy/core';

export interface MediaProbe {
  mime_type?: string; content_type?: string; video_content_type?: string; audio_content_type?: string;
  video_codec?: string; audio_codec?: string; width?: number; height?: number;
  framerate?: number; bitrate?: number; timestamp_repair?: boolean;
}

export function nativeAv1Supported(): boolean {
  const video = document.createElement('video');
  return ['av01.0.08M.08', 'av01.0.08M.10'].every(codec => !!video.canPlayType(`video/mp4; codecs="${codec}"`));
}

export async function browserSupportsMedia(probe: MediaProbe): Promise<boolean> {
  if (!probe.content_type) return false;
  const playable = !!document.createElement('video').canPlayType(probe.content_type);
  const capabilities = navigator.mediaCapabilities;
  if (!capabilities?.decodingInfo || !probe.video_content_type || !probe.width || !probe.height || !probe.bitrate || !probe.framerate) return playable;
  try {
    const result = await capabilities.decodingInfo({ type: 'file', ...(probe.audio_content_type ? { audio: { contentType: probe.audio_content_type } } : {}), video: {
      contentType: probe.video_content_type, width: probe.width, height: probe.height,
      bitrate: probe.bitrate, framerate: probe.framerate,
    } });
    return result.supported || playable;
  } catch { return playable; }
}

export async function nativePreviewSource(id: number, session: string): Promise<{ src: string; type: string } | null> {
  const result = await api(`/api/stream-plan?id=${id}&session=${encodeURIComponent(session)}&probe_only=true`) as { probe?: MediaProbe } | null;
  if (!result?.probe || result.probe.timestamp_repair || !await browserSupportsMedia(result.probe)) return null;
  return { src: `/stream?id=${id}&session=${encodeURIComponent(session)}&native_play=true&preview=true`, type: result.probe.mime_type || 'video/mp4' };
}
