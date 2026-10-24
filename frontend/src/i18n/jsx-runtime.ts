/** React JSX 的呈现边界仅翻译目录中的文案，不改写协议、表单值和媒体元数据。 */
import { jsx as reactJsx, jsxs as reactJsxs } from 'react/jsx-runtime';
import { translate } from './index';
export { Fragment } from 'react/jsx-runtime';
export type { JSX } from 'react/jsx-runtime';

const TEXT_PROPS = ['label', 'title', 'description', 'hint', 'placeholder', 'summary', 'lede', 'status',
  'aria-label', 'aria-description', 'alt', 'textValue', 'emptyLabel', 'loadingLabel'];
function children(value: unknown): unknown {
  if (typeof value === 'string') return translate(value);
  if (Array.isArray(value)) return value.map(children);
  return value;
}
export function localized(type: unknown, value: unknown) {
  if (!value || typeof value !== 'object' || ['script', 'style', 'code', 'pre', 'textarea'].includes(String(type))) return value;
  const props = value as Record<string, unknown>;
  if (['data-i18n-ignore', 'data-detail-title', 'data-item-title', 'data-card-title', 'data-entity-name',
    'data-creator-name', 'data-middle-truncate'].some(key => Object.hasOwn(props, key))) return props;
  const result = { ...props };
  if ('children' in props) result.children = children(props.children);
  for (const key of TEXT_PROPS) if (typeof props[key] === 'string') result[key] = translate(props[key]);
  return result;
}
export const jsx: typeof reactJsx = (type, props, key) => reactJsx(type, localized(type, props), key);
export const jsxs: typeof reactJsxs = (type, props, key) => reactJsxs(type, localized(type, props), key);
