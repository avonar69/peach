import { nativePreviewSource } from '../media-capabilities';
import { cancelStreamSession, newStreamSession } from '../media-sessions';

/** 单个浏览器解码器只捕获悬停位置，最多保存二十帧内存缓存。 */
export class OnDemandPreview {
  private video = document.createElement('video');
  private canvas = document.createElement('canvas');
  private cache = new Map<number, string>();
  private timer: ReturnType<typeof setTimeout> | undefined;
  private abort: AbortController | undefined;
  private session = '';
  private generation = 0;
  private revision = 0;
  private busy = false;
  private disposed = false;
  private unavailable = false;
  private latest: { seconds: number; revision: number; show(frame: string | null): void } | null = null;

  constructor(private id: number) {
    this.video.muted = true;
    this.video.playsInline = true;
    this.video.preload = 'metadata';
  }

  request(seconds: number, show: (frame: string | null) => void) {
    if (this.disposed) return;
    if (this.unavailable) { show(null); return; }
    const rounded = Math.floor(seconds), revision = ++this.revision;
    const saved = this.cache.get(rounded);
    if (saved) { this.latest = null; clearTimeout(this.timer); show(saved); return; }
    this.latest = { seconds: rounded, revision, show };
    clearTimeout(this.timer);
    this.timer = setTimeout(() => { void this.render() }, 140);
  }

  private wait(event: string, signal: AbortSignal): Promise<void> {
    return new Promise((resolve, reject) => {
      const cleanup = () => { clearTimeout(timer); this.video.removeEventListener(event, done); this.video.removeEventListener('error', failed); signal.removeEventListener('abort', failed) };
      const done = () => { cleanup(); resolve() };
      const failed = () => { cleanup(); reject(new Error('Preview decoding unavailable')) };
      const timer = setTimeout(failed, 6000);
      this.video.addEventListener(event, done, { once: true });
      this.video.addEventListener('error', failed, { once: true });
      signal.addEventListener('abort', failed, { once: true });
      if (signal.aborted) failed();
    });
  }

  private async render() {
    if (this.busy || !this.latest || this.disposed) return;
    const target = this.latest;
    this.latest = null;
    const saved = this.cache.get(target.seconds);
    if (saved) { if (target.revision === this.revision) target.show(saved); return; }
    this.busy = true;
    const generation = this.generation;
    const abort = new AbortController();
    this.abort = abort;
    try {
      if (!this.session) {
        this.session = newStreamSession();
        const source = await nativePreviewSource(this.id, this.session);
        if (!source || generation !== this.generation) throw new Error('Native preview unavailable');
        const ready = this.wait('loadedmetadata', abort.signal);
        this.video.src = source.src;
        this.video.load();
        await ready;
      }
      if (generation !== this.generation) return;
      const time = Math.max(.001, Math.min(target.seconds, Math.max(.001, this.video.duration - .05)));
      const ready = this.wait('seeked', abort.signal);
      this.video.currentTime = time;
      await ready;
      if (generation !== this.generation || this.disposed) return;
      this.canvas.width = 240;
      this.canvas.height = Math.max(1, Math.round(240 * (this.video.videoHeight || 9) / (this.video.videoWidth || 16)));
      this.canvas.getContext('2d')!.drawImage(this.video, 0, 0, this.canvas.width, this.canvas.height);
      const frame = this.canvas.toDataURL('image/jpeg', .8);
      if (this.cache.size >= 20) this.cache.delete(this.cache.keys().next().value!);
      this.cache.set(target.seconds, frame);
      if (target.revision === this.revision) target.show(frame);
    } catch {
      if (generation === this.generation) {
        this.unavailable = true;
        if (target.revision === this.revision) target.show(null);
      }
      this.releaseDecoder();
    } finally {
      this.busy = false;
      if (this.latest && !this.disposed && !this.unavailable) this.timer = setTimeout(() => { void this.render() }, 140);
    }
  }

  private releaseDecoder() {
    if (this.session) cancelStreamSession(this.session);
    this.session = '';
    this.video.pause();
    this.video.removeAttribute('src');
    this.video.load();
  }

  cancel() {
    this.latest = null;
    this.generation++;
    clearTimeout(this.timer);
    this.abort?.abort();
    this.releaseDecoder();
  }

  dispose() { this.disposed = true; this.cancel(); this.cache.clear() }
}
