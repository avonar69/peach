// 离线检查已审计源文案的覆盖率和参数保留情况。
import { readFile } from 'node:fs/promises';
const read = async name => JSON.parse(await readFile(new URL(`../src/i18n/${name}`, import.meta.url), 'utf8'));
const [manual, generated, inventory] = await Promise.all([read('en.json'), read('en.generated.json'), read('inventory.json')]);
const catalog = { ...generated, ...manual };
const missing = inventory.entries.filter(entry => !Object.hasOwn(catalog, entry.source));
const parameters = value => [...new Set(value.match(/\{(?:\d+|[a-zA-Z_]\w*)\}/g) || [])].sort().join(',');
const invalid = Object.entries(catalog).filter(([source, english]) => parameters(source) !== parameters(english));
const custom = await read('custom-inventory.json');
for (const language of ['es', 'fr', 'de', 'pt-BR', 'ja', 'ko', 'vi', 'zh-TW', 'zh-CN']) {
  const locale = await read(`${language}.json`);
  if (language !== 'zh-CN') for (const entry of inventory.entries) if (!Object.hasOwn(locale, entry.source)) missing.push({ ...entry, language });
  for (const source of custom) if (!Object.hasOwn(locale, source)) missing.push({ source, language });
  invalid.push(...Object.entries(locale).filter(([source, target]) => parameters(source) !== parameters(target)));
}
if (missing.length || invalid.length) {
  console.error(JSON.stringify({ missing, invalid }, null, 2));
  process.exitCode = 1;
} else console.log(`${inventory.entries.length} public source candidates and ${custom.length} authored UI strings covered; all template parameters preserved`);
