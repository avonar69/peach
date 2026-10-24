import { Select, SelectItem } from '@/components/base/select/select';
import { getLanguage, setLanguage } from '../../i18n';
import { isLanguage, LANGUAGES } from '../../i18n/languages';

export function LanguageSelect() {
  return <Select aria-label="Language" selectedKey={getLanguage()}
    onSelectionChange={(key) => { if (isLanguage(key)) setLanguage(key); }}>
    {LANGUAGES.map(([key, label]) => <SelectItem key={key} id={key} textValue={label}><span data-i18n-ignore="">{label}</span></SelectItem>)}
  </Select>;
}
