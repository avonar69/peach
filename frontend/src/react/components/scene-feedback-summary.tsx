/* 个人作品评分和偏好计数共用在资料页与名册卡片。 */
import { RiStarLine, RiThumbUpLine, RiThumbDownLine } from '@remixicon/react';
import { translate } from '../../i18n';

export interface SceneFeedback {
  average_stars: number | null;
  rated_count: number;
  thumbs_up: number;
  thumbs_down: number;
}

export function SceneFeedbackSummary({ value }: { value?: SceneFeedback | null }) {
  if (!value) return null;
  const average = value.average_stars === null ? '—' : `${Number(value.average_stars.toFixed(2))} / 5`;
  return <span data-scene-feedback="" className="inline-flex max-w-full flex-wrap items-center gap-x-3 gap-y-1 text-caption-1-regular text-text-secondary">
    <span className="inline-flex items-center gap-1" title="Average scene rating" role="img" aria-label={`${translate('Average scene rating')}: ${average}`}>
      <RiStarLine className="size-4 shrink-0" aria-hidden /><span data-i18n-ignore="">{average}</span>
    </span>
    <span title="Rated scenes" role="img" aria-label={`${translate('Rated scenes')}: ${value.rated_count}`} data-i18n-ignore="">({value.rated_count})</span>
    <span className="inline-flex items-center gap-1" title="Thumbs up" role="img" aria-label={`${translate('Thumbs up')}: ${value.thumbs_up}`}>
      <RiThumbUpLine className="size-4 shrink-0" aria-hidden /><span data-i18n-ignore="">{value.thumbs_up}</span>
    </span>
    <span className="inline-flex items-center gap-1" title="Thumbs down" role="img" aria-label={`${translate('Thumbs down')}: ${value.thumbs_down}`}>
      <RiThumbDownLine className="size-4 shrink-0" aria-hidden /><span data-i18n-ignore="">{value.thumbs_down}</span>
    </span>
  </span>;
}
