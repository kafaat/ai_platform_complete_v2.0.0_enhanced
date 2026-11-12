import { dateHasPersistedCog, type PersistedCogDate } from '../maphub/persistedCog';

export function satelliteArchiveLayer(
  mode: 'scouting' | 'vegetation' | 'truecolor',
  index: string,
  selected: string,
  dates: readonly PersistedCogDate[],
  measuredDates: readonly { datetime: string }[],
) {
  const day = selected.slice(0, 10);
  const product = mode === 'truecolor' ? 'truecolor' : index;
  const stored = dateHasPersistedCog(product, day, dates) ||
    (mode !== 'truecolor' && measuredDates.some(p => day === 'latest' || p.datetime.slice(0, 10) === day));
  return {
    stored,
    index: mode === 'truecolor' && !stored ? index : product,
    segment: stored ? 'tiles' as const : 'cdse-tiles' as const,
    opacity: mode === 'truecolor' ? (stored ? 1 : 0) : 0.75,
  };
}
