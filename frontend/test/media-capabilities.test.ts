import { afterEach, expect, it, vi } from 'vitest';
import { browserSupportsMedia } from '../src/media-capabilities';

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() });

it('按视频与音频组合查询浏览器，支持 HEVC 而不依赖浏览器名称', async () => {
  const canPlay = vi.spyOn(HTMLMediaElement.prototype, 'canPlayType').mockReturnValue('probably');
  expect(await browserSupportsMedia({ content_type: 'video/mp4; codecs="hvc1.2.4.L120.B0,ec-3"' })).toBe(true);
  expect(canPlay).toHaveBeenCalledWith('video/mp4; codecs="hvc1.2.4.L120.B0,ec-3"');
  canPlay.mockReturnValue('');
  expect(await browserSupportsMedia({ content_type: 'video/mp4; codecs="hvc1.2.4.L120.B0,ec-3"' })).toBe(false);
});

it('没有可靠的容器编码描述时不猜测支持', async () => {
  expect(await browserSupportsMedia({})).toBe(false);
});

it('任一浏览器能力接口报告可用即可尝试原片，不以性能提示禁用直读', async () => {
  const canPlay = vi.spyOn(HTMLMediaElement.prototype, 'canPlayType').mockReturnValue('probably');
  const decodingInfo = vi.fn().mockResolvedValue({ supported: false, smooth: false, powerEfficient: false });
  vi.stubGlobal('navigator', { mediaCapabilities: { decodingInfo } });
  const probe = { content_type: 'video/mp4; codecs="hvc1.2.4.L120.B0,mp4a.40.2"', video_content_type: 'video/mp4; codecs="hvc1.2.4.L120.B0"', audio_content_type: 'audio/mp4; codecs="mp4a.40.2"',
    width: 1920, height: 1080, bitrate: 4000000, framerate: 30 };
  expect(await browserSupportsMedia(probe)).toBe(true);
  expect(decodingInfo.mock.calls[0]![0].audio.contentType).toBe(probe.audio_content_type);
  canPlay.mockReturnValue('');
  decodingInfo.mockResolvedValue({ supported: true, smooth: true, powerEfficient: true });
  expect(await browserSupportsMedia(probe)).toBe(true);
  decodingInfo.mockRejectedValue(new TypeError('Unavailable API'));
  expect(await browserSupportsMedia(probe)).toBe(false);
});
