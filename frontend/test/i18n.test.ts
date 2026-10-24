import { afterEach, describe, expect, it, vi } from 'vitest';
import { translate } from '../src/i18n';
import { jsx } from '../src/i18n/jsx-runtime';

afterEach(() => localStorage.removeItem('peach.language'));
describe('interface localization', () => {
  it('uses bundled catalogs for every additional language and preserves dynamic parameters', async () => {
    const { LANGUAGES, localeCatalogs } = await import('../src/i18n/languages');
    for (const [key] of LANGUAGES) {
      if (key === 'en' || key === 'zh-CN') continue;
      localStorage.setItem('peach.language', key);
      const locale = localeCatalogs[key]!;
      expect(translate('横屏')).toBe(locale['横屏']);
      expect(translate('自动匹配厂牌')).toBe(locale['自动匹配厂牌']);
      expect(translate('未找到：openssl')).toContain('openssl');
      expect(translate('读取媒体属性与生成预览')).toBe(locale['读取媒体属性与生成预览']);
      expect(translate('Interface language')).toBe(locale['Interface language']);
      expect(translate('Unknown.Movie.mp4')).toBe('Unknown.Movie.mp4');
    }
  });
  it('defaults to English and translates static and parameterized copy', async () => {
    localStorage.removeItem('peach.language');
    vi.resetModules();
    const fresh = await import('../src/i18n');
    expect(fresh.getLanguage()).toBe('en');
    localStorage.setItem('peach.language', 'en');
    expect(translate('完成设置')).toBe('Finish setup');
    expect(translate('完成设置后扫描这 12 个文件夹并补全资料')).toBe('Scan 12 folders and fetch metadata after setup');
    expect(translate('未知媒体标题.mp4')).toBe('未知媒体标题.mp4');
  });
  it('supports the original Chinese interface', () => {
    localStorage.setItem('peach.language', 'zh-CN');
    expect(translate('完成设置')).toBe('完成设置');
  });
  it('translates accessible presentation without changing form values or identifiers', () => {
    localStorage.setItem('peach.language', 'en');
    const element = jsx('button', { children: '保存', 'aria-label': '保存', value: '保存', id: '保存' });
    expect(element.props).toEqual({ children: 'Save', 'aria-label': 'Save', value: '保存', id: '保存' });
    expect((jsx('code', { children: '保存' }).props as { children: string }).children).toBe('保存');
    expect((jsx('span', { 'data-detail-title': '', children: '未评分' }).props as { children: string }).children).toBe('未评分');
  });
});
