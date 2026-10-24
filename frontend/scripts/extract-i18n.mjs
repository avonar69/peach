// 从自有前端源码提取静态文案和带参数文案，不读取媒体或运行数据。
import { readdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { parseSync } from 'oxc-parser';
import { execFileSync } from 'node:child_process';

const root = fileURLToPath(new URL('../src', import.meta.url));
const output = process.argv[2];
const publicBase = process.argv.includes('--public-base');
if (!output) throw Error('Specify an output JSON file');
const entries = new Map();
function record(text, filename) {
  if (typeof text !== 'string' || !/[\u3400-\u9fff]/.test(text)) return;
  const value = text.trim();
  if (!value || value.length > 12000) return;
  const locations = entries.get(value) || new Set();
  locations.add(path.relative(root, filename).replaceAll('\\', '/'));
  entries.set(value, locations);
}
function visit(node, filename) {
  if (!node || typeof node !== 'object') return;
  if (node.type === 'TemplateLiteral') {
    record(node.quasis.map((part, index) => (part.value.cooked || part.value.raw)
      + (index < node.expressions.length ? `{${index}}` : '')).join(''), filename);
    for (const expression of node.expressions) visit(expression, filename);
    return;
  }
  if (node.type === 'StringLiteral' || node.type === 'Literal') record(node.value, filename);
  if (node.type === 'JSXText') record(node.value.replace(/\s+/g, ' '), filename);
  for (const [key, value] of Object.entries(node)) {
    if (key === 'comments' || key === 'loc' || key === 'span') continue;
    if (Array.isArray(value)) value.forEach(child => visit(child, filename));
    else if (value && typeof value === 'object') visit(value, filename);
  }
}
async function walk(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const filename = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      if (!['i18n', 'boardui', 'evilcharts'].includes(entry.name)) await walk(filename);
    } else if (/\.(ts|tsx|js)$/.test(entry.name) && !entry.name.endsWith('.d.ts')) {
      let code;
      if (publicBase) {
        try { code = execFileSync('git', ['show', `HEAD:frontend/src/${path.relative(root, filename).replaceAll('\\', '/')}`], { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }); }
        catch { continue; }
      } else code = await readFile(filename, 'utf8');
      const parsed = parseSync(filename, code);
      if (parsed.errors.length) throw Error(`${filename}: ${JSON.stringify(parsed.errors)}`);
      visit(parsed.program, filename);
    }
  }
}
await walk(root);
await writeFile(output, JSON.stringify([...entries].map(([source, locations]) => ({ source, locations: [...locations] })), null, 2));
console.log(`${entries.size} source strings extracted`);
