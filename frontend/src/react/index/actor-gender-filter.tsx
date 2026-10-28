import { ACTOR_GENDERS } from '../../actor-genders';
import { MultiChoiceMenu } from '../components/multi-choice-menu';

export function ActorGenderFilter({ value, onChange }: { value: string; onChange(keys: Iterable<string>): void }) {
  const selected = value === 'all' ? ACTOR_GENDERS.map(([key]) => key) : value.split(',');
  return <MultiChoiceMenu label="Actor genders" symbol="user-round" selected={selected} onChange={onChange}
    options={ACTOR_GENDERS.map(([id, label]) => ({ id, label }))} />;
}
