/** 本机浏览器的实验性能偏好；未开启时沿用标准请求节律。 */
export function performancePreferences(storage?: Pick<Storage, 'getItem'>): { video: boolean; ui: boolean; onDemand: boolean } {
  try {
    const settings = JSON.parse((storage ?? localStorage).getItem('peach.settings.v1') || '{}');
    return { video: settings?.betaFastVideo === true, ui: settings?.betaFastUI === true, onDemand: settings?.onDemandSeekPreviews === true };
  } catch { return { video: false, ui: false, onDemand: false }; }
}

/** 只为浏览用快照复用短期缓存；任务、复核与配置保持各自的即时请求。 */
export function navigationFreshness(key: readonly unknown[]): number {
  return performancePreferences().ui && ['stats', 'taste', 'index', 'entity', 'entity-photos'].includes(String(key[0])) ? 30_000 : 0;
}
