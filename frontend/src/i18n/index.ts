import en from './en.json';
import generated from './en.generated.json';
import { isLanguage, localeCatalogs, type Language } from './languages';
export type { Language } from './languages';

const KEY = 'peach.language';
let startupLanguage: Language = 'en';
try { const value = localStorage.getItem(KEY); if (isLanguage(value)) startupLanguage = value; } catch { /* 使用默认语言。 */ }
export function getLanguage(): Language {
  try {
    const stored = localStorage.getItem(KEY);
    return isLanguage(stored) ? stored : startupLanguage;
  } catch { return startupLanguage; }
}
export function setLanguage(language: Language): void {
  if (!isLanguage(language)) return;
  localStorage.setItem(KEY, language);
  if (document.getElementById('peach-page')) { location.reload(); return; }
  void fetch('/api/configuration/interface-language', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ language }), keepalive: true }).catch(() => undefined).finally(() => location.reload());
}
export const catalog: Readonly<Record<string, string>> = { ...generated, ...en };
function activeCatalog(): Readonly<Record<string, string>> {
  return localeCatalogs[getLanguage()] ?? catalog;
}
const placeholder = /\{([a-zA-Z_][\w]*|\d+)\}/g;
const escapePattern = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const knownParts = new RegExp(Object.keys(catalog).filter(key => key.length <= 100 && !key.includes('{')
  && /[\u3400-\u9fff]/.test(key)).sort((a, b) => b.length - a.length).map(escapePattern).join('|'), 'g');
function translateKnownParts(value: string): string {
  if (getLanguage() === 'zh-CN') return value;
  if (!/[\u3400-\u9fff]/.test(value)) return value;
  const selected = activeCatalog();
  const translated = value.replace(knownParts, key => ` ${selected[key] ?? catalog[key]} `).replace(/\s+/g, ' ').trim();
  return /[\u3400-\u9fff]/.test(translated) ? value : translated;
}
function buildTemplates(selected: Readonly<Record<string, string>>, includeBase = true) { return Object.entries({ ...(includeBase ? catalog : {}), ...selected }).flatMap(([source, english]) => {
  const matches = [...source.matchAll(placeholder)];
  if (!matches.length) return [];
  let offset = 0, pattern = '^';
  for (const match of matches) {
    pattern += escapePattern(source.slice(offset, match.index)) + '(.+?)';
    offset = match.index! + match[0].length;
  }
  pattern += escapePattern(source.slice(offset)) + '$';
  return [{ prefix: source.slice(0, matches[0]!.index), source, english, matches,
    literalLength: source.replace(placeholder, '').length, curated: Object.hasOwn(en, source), pattern: new RegExp(pattern),
    partial: source.endsWith('}') ? null : new RegExp(pattern.slice(0, -1)) }];
}).sort((a, b) => b.literalLength - a.literalLength || Number(b.curated) - Number(a.curated)); }
const templateCache = new Map<Language, ReturnType<typeof buildTemplates>>();
export function translate(text: string): string {
  const language = getLanguage();
  const trimmed = text.trim();
  const normalized = trimmed.replace(/\s+/g, ' ');
  const selected = activeCatalog();
  const translated = selected[trimmed] ?? selected[normalized] ?? (language === 'zh-CN' ? undefined : catalog[trimmed] ?? catalog[normalized]);
  if (translated !== undefined) return text.replace(trimmed, translated);
  if (language === 'en' && !/[\u3400-\u9fff]/.test(text)) return text;
  if (language === 'zh-CN' && /[\u3400-\u9fff]/.test(text)) return text;
  const shortcut = normalized.match(/^(.*?)((?:\s+(?:alt|ctrl|shift|meta)\+\S+)+)$/i);
  if (shortcut) return text.replace(trimmed, translate(shortcut[1]!) + shortcut[2]);
  if (!templateCache.has(language)) templateCache.set(language, buildTemplates(selected, language !== 'zh-CN'));
  for (const template of templateCache.get(language)!) {
    if (template.prefix && !normalized.startsWith(template.prefix)) continue;
    const match = template.pattern.exec(normalized);
    if (!match) {
      if (!template.prefix || template.literalLength < 4 || !template.partial) continue;
      const partial = template.partial.exec(normalized);
      if (!partial || partial[0].length >= normalized.length) continue;
      const values = new Map(template.matches.map((entry, index) => [entry[1], partial[index + 1]!]));
      const first = template.english.replace(placeholder, (original, key: string) => values.get(key) ?? original);
      return text.replace(trimmed, `${translateKnownParts(first).trimEnd()} ${translate(normalized.slice(partial[0].length))}`);
    }
    const values = new Map(template.matches.map((entry, index) => {
      const value = match[index + 1]!;
      return [entry[1], selected[value] ?? catalog[value] ?? value];
    }));
    const english = template.english.replace(placeholder, (original, key: string) => values.get(key) ?? original);
    return text.replace(trimmed, translateKnownParts(english));
  }
  if (language === 'zh-CN') return text;
  const scan = trimmed.match(/^完成设置后扫描并补全资料：(.+)$/);
  if (scan) return `Scan and fetch metadata after setup: ${scan[1]}`;
  const folders = trimmed.match(/^完成设置后扫描这 (\d+) 个文件夹并补全资料$/);
  if (folders) return `Scan ${folders[1]} folders and fetch metadata after setup`;
  const numbered = trimmed.match(/^(媒体库|媒体来源|媒体读取策略) (\d+)$/);
  if (numbered) return `${catalog[numbered[1]!] || 'Media access policy'} ${numbered[2]}`;
  const missing = trimmed.match(/^未检测到 (.+)。$/);
  if (missing) return `${missing[1]} was not detected.`;
  const download = trimmed.match(/^下载 (.+)$/);
  if (download) return `Download ${download[1]}`;
  return text;
}

export function applyLanguage(): void {
  document.documentElement.lang = getLanguage();
}

/** 先翻译固定模板，再一次性填入值，保留文件名里的占位字符。 */
export function formatTranslation(template: string, ...values: string[]): string {
  return translate(template).replace(/\{(\d+)\}/g, (original, key: string) => values[Number(key)] ?? original);
}
if (typeof document !== 'undefined') applyLanguage();
