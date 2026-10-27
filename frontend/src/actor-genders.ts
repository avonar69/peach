/** 本浏览器的演员性别筛选，同时用于名册与随机演员。 */
export const ACTOR_GENDERS = [
  ['FEMALE', 'Female'], ['MALE', 'Male'], ['TRANSGENDER_FEMALE', 'Transgender female'],
  ['TRANSGENDER_MALE', 'Transgender male'], ['INTERSEX', 'Intersex'], ['NON_BINARY', 'Non-binary'],
  ['UNKNOWN', 'Unknown'],
] as const;
const KEY = 'peach.actor-genders.v1';
export function actorGenderSelection(): string {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(KEY) || 'null');
    if (Array.isArray(value)) return ACTOR_GENDERS.filter(([key]) => value.includes(key)).map(([key]) => key).join(',') || 'none';
  } catch { /* 无效或受限存储使用全部。 */ }
  return 'all';
}
export function saveActorGenders(keys: Iterable<string>): string {
  const selected = new Set(keys);
  const values = ACTOR_GENDERS.filter(([key]) => selected.has(key)).map(([key]) => key);
  try { localStorage.setItem(KEY, JSON.stringify(values)) } catch { /* 受限存储保留本页选择。 */ }
  return values.join(',') || 'none';
}
