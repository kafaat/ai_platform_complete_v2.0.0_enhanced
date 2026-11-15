import { acquisitionUtcDay } from '../../lib/dates';
import { dateHasPersistedCog, type PersistedCogDate } from '../maphub/persistedCog';

export function satelliteArchiveLayer(
  mode: 'scouting' | 'vegetation' | 'truecolor',
  index: string,
  selected: string,
  dates: readonly PersistedCogDate[],
  measuredDates: readonly { datetime: string }[],
) {
  const day = acquisitionUtcDay(selected);
  const product = mode === 'truecolor' ? 'truecolor' : index;
  const stored = dateHasPersistedCog(product, selected, dates) ||
    (mode !== 'truecolor' && measuredDates.some(p => {
      const measuredDay = acquisitionUtcDay(p.datetime);
      return !!measuredDay && (selected === 'latest' || measuredDay === day);
    }));
  return {
    stored,
    index: mode === 'truecolor' && !stored ? index : product,
    segment: stored ? 'tiles' as const : 'cdse-tiles' as const,
    opacity: mode === 'truecolor' ? (stored ? 1 : 0) : 0.75,
  };
}
