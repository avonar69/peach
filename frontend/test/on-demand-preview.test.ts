import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { nativePreviewSource } from '../src/media-capabilities';
import { OnDemandPreview } from '../src/player/on-demand-preview';

vi.mock('../src/media-capabilities', () => ({ nativePreviewSource: vi.fn() }));
const native = vi.mocked(nativePreviewSource);
const draw = vi.fn();

beforeEach(() => {
  vi.useFakeTimers();
  native.mockReset();
  native.mockResolvedValue({ src: '/stream?id=1&preview=true&native_play=true', type: 'video/mp4' });
  draw.mockClear();
  vi.stubGlobal('fetch', vi.fn(async () => new Response('{"cancelled":1}', { headers: { 'Content-Type': 'application/json' } })));
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, 'duration', 'get').mockReturnValue(100);
  vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(function(this: HTMLMediaElement) {
    if (this.getAttribute('src')) queueMicrotask(() => this.dispatchEvent(new Event('loadedmetadata')));
  });
  vi.spyOn(HTMLMediaElement.prototype, 'currentTime', 'set').mockImplementation(function(this: HTMLMediaElement) {
    queueMicrotask(() => this.dispatchEvent(new Event('seeked')));
  });
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ drawImage: draw } as unknown as CanvasRenderingContext2D);
  vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue('data:image/jpeg;base64,frame');
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() });

it('合并快速移动，只解最后位置，重复位置复用内存', async () => {
  const preview = new OnDemandPreview(1), first = vi.fn(), last = vi.fn();
  preview.request(5, first);
  preview.request(20, last);
  await vi.advanceTimersByTimeAsync(200);
  expect(first).not.toHaveBeenCalled();
  expect(last).toHaveBeenCalledWith('data:image/jpeg;base64,frame');
  preview.request(20.5, last);
  expect(native).toHaveBeenCalledOnce();
  expect(draw).toHaveBeenCalledOnce();
  preview.dispose();
});

it('不兼容片源不重复请求，也不发起转换', async () => {
  native.mockResolvedValue(null);
  const preview = new OnDemandPreview(1), show = vi.fn();
  preview.request(5, show);
  await vi.advanceTimersByTimeAsync(200);
  preview.request(10, show);
  await vi.advanceTimersByTimeAsync(200);
  expect(native).toHaveBeenCalledOnce();
  expect(draw).not.toHaveBeenCalled();
  expect(show).toHaveBeenCalledWith(null);
  preview.dispose();
});

it('离开时间轴时取消自身会话，迟到响应不能显示画面', async () => {
  let resolve!: (value: { src: string; type: string }) => void;
  native.mockReturnValue(new Promise(done => { resolve = done }));
  const preview = new OnDemandPreview(1), show = vi.fn();
  preview.request(5, show);
  await vi.advanceTimersByTimeAsync(150);
  preview.cancel();
  resolve({ src: '/stream?id=1', type: 'video/mp4' });
  await vi.advanceTimersByTimeAsync(200);
  expect(show).not.toHaveBeenCalled();
  expect(draw).not.toHaveBeenCalled();
  expect(vi.mocked(fetch).mock.calls[0]?.[0]).toContain('/api/stream-cancel?session=');
  preview.dispose();
});
