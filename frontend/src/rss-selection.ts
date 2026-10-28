/** RSS 多选只属于当前浏览器；null 表示包含以后新增的所有来源。 */
const KEY = 'peach.rss-selected-feeds.v1';
export function rssSelection(): string[] | null {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(KEY) || 'null');
    return Array.isArray(value) ? [...new Set(value.filter((id): id is string => typeof id === 'string' && /^[1-9]\d*$/.test(id)))] : null;
  } catch { return null }
}
export function saveRSSSelection(value: string[] | null): void {
  try { if (value === null) localStorage.removeItem(KEY); else localStorage.setItem(KEY, JSON.stringify(value)) } catch { /* 当前页面保留选择。 */ }
}
