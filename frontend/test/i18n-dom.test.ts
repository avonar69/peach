import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { installDomLocalization, localizeDom } from '../src/i18n/dom';
import { translate } from '../src/i18n';
import { popCount } from '../src/ui-kit/motion';

let stop = () => {};
beforeEach(() => { localStorage.setItem('peach.language', 'en'); document.body.innerHTML = ''; });
afterEach(() => { stop(); document.body.innerHTML = ''; localStorage.setItem('peach.language', 'zh-CN'); });
const flush = () => new Promise(resolve => setTimeout(resolve, 0));

describe('imperative interface localization', () => {
  it('localizes document titles while observing a body-only application root', async () => {
    document.title = '外观与导航';
    stop = installDomLocalization(document.body);
    expect(document.title).toBe('Appearance & navigation');
    document.title = '扫描与采集';
    await flush();
    expect(document.title).not.toMatch(/[\u3400-\u9fff]/);
  });
  it('covers backend scan steps, orientation facets and diagnostics reasons with counts', () => {
    document.body.innerHTML = '<aside><span>读取媒体属性与生成预览</span><span>采集外部资料与封面</span></aside>'
      + '<nav><button>横屏</button><button>竖屏</button></nav>'
      + '<section><summary>识别失败 · 0 项</summary><summary>补资料失败 · 0 项</summary><summary>缺封面 · 0 项</summary><summary>缺时长 · 0 项</summary>'
      + '<p>未找到：openssl</p><p>尚无检查或解析记录，可在来源和凭证中检查连接</p></section>';
    localizeDom(document.body);
    expect(document.body.textContent).not.toMatch(/[\u3400-\u9fff]/);
    expect(document.querySelector('aside')?.textContent).toContain('Read media properties and generate previews');
    expect(document.querySelector('nav')?.textContent).toBe('LandscapePortrait');
    expect(document.querySelector('section')?.textContent).toContain('Not found: openssl');
    expect(document.querySelector('section')?.textContent).toContain('Identification failed');
  });
  it('covers tutorial, top bar, popup copy and accessibility attributes without changing inputs', () => {
    document.body.innerHTML = '<nav><button title="外观与导航" aria-label="外观与导航">外观与导航</button><span>没看过</span><span>高潮计数</span></nav>'
      + '<aside><p>完成 Peach 的安装教程</p><p>已处理 2/6 项。</p><button>跳过</button></aside>'
      + '<input value="外观与导航" placeholder="外观与导航"><select><option>未评分</option></select>';
    localizeDom(document.body);
    expect(document.querySelector('nav')?.textContent).toBe('Appearance & navigationUnwatchedOrgasm count');
    expect(document.querySelector('button')?.getAttribute('aria-label')).toBe('Appearance & navigation');
    expect(document.querySelector('aside')?.textContent).toContain('Completed 2/6 steps.');
    expect(document.querySelector('input')?.value).toBe('外观与导航');
    expect(document.querySelector('input')?.placeholder).toBe('Appearance & navigation');
    expect(document.querySelector('option')?.textContent).toBe('Unrated');
    expect(document.querySelector('option')?.value).toBe('未评分');
  });
  it('translates dynamic portals, notifications, text and attribute changes', async () => {
    stop = installDomLocalization();
    const popup = document.createElement('div');
    document.body.append(popup);
    popup.innerHTML = '<button title="浏览与播放">浏览与播放</button>';
    await flush();
    expect(popup.textContent).toBe('Browsing & playback');
    const button = popup.querySelector('button')!;
    button.textContent = '真实观看';
    button.title = '离开位置';
    await flush();
    expect(button.textContent).toBe('Watched coverage');
    expect(button.title).toBe('Last playback position');
    await flush();
    expect(button.textContent).toBe('Watched coverage');
  });
  it('preserves media titles, editable values and code', () => {
    document.body.innerHTML = '<span data-item-title>未评分</span><code>没看过</code>'
      + '<div contenteditable="true">外观与导航</div><span data-middle-truncate>真实观看</span>';
    localizeDom(document.body);
    expect(document.body.textContent).toBe('未评分没看过外观与导航真实观看');
  });
  it('keeps the Chinese interface and localizes parameters without losing values', () => {
    expect(translate('继续：设置采集来源与凭证')).toBe('Continue: Set up metadata sources & credentials');
    expect(translate('已经导入 17 项馆藏。')).toBe('Imported 17 library items.');
    localStorage.setItem('peach.language', 'zh-CN');
    document.body.innerHTML = '<button>外观与导航</button>';
    localizeDom(document.body);
    expect(document.body.textContent).toBe('外观与导航');
  });
  it('translates counters before character animation and resolves composite accessible sort labels', () => {
    const count = document.createElement('span');
    popCount(count, '7 个符合 · 显示 7');
    expect(count.textContent).toBe('7 matches · Showing 7');
    expect(translate('按评分从高到低排序')).not.toMatch(/[\u3400-\u9fff]/);
    expect(translate('扫描与资料采集已完成：识别 8 个番号，整理 65 组资料结果，自动保存 0 条'))
      .not.toMatch(/[\u3400-\u9fff]/);
    expect(translate('通知 alt+T')).toBe('Notifications alt+T');
  });
});
