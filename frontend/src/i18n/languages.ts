import es from './es.json';
import fr from './fr.json';
import de from './de.json';
import pt from './pt-BR.json';
import ja from './ja.json';
import ko from './ko.json';
import vi from './vi.json';
import tw from './zh-TW.json';
import cn from './zh-CN.json';

export const LANGUAGES = [
  ['en', 'English'], ['zh-CN', '简体中文'], ['zh-TW', '繁體中文'], ['es', 'Español'],
  ['fr', 'Français'], ['de', 'Deutsch'], ['pt-BR', 'Português (Brasil)'],
  ['ja', '日本語'], ['ko', '한국어'], ['vi', 'Tiếng Việt'],
] as const;
export type Language = typeof LANGUAGES[number][0];
export const localeCatalogs: Partial<Record<Language, Record<string, string>>> = {
  es, fr, de, 'pt-BR': pt, ja, ko, vi, 'zh-TW': tw, 'zh-CN': cn,
};
export function isLanguage(value: unknown): value is Language {
  return LANGUAGES.some(([key]) => key === value);
}
