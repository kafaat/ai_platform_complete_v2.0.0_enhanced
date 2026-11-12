import { expect, it } from 'vitest';
import { satelliteArchiveLayer } from './satelliteArchive';

const date = '2024-10-23';
const stored = [{ date, indices: ['NDRE'], has_cog: true }];
it('reads a stored index on the selected acquisition day', () => {
  expect(satelliteArchiveLayer('vegetation','ndre',date+'T07:30:00Z',stored,[]).segment).toBe('tiles');
  expect(satelliteArchiveLayer('vegetation','ndmi',date,stored,[]).segment).toBe('cdse-tiles');
  expect(satelliteArchiveLayer('vegetation','ndre','2025-10-23',stored,[]).stored).toBe(false);
});
it('does not promote a catalogue-only row to a stored product', () => {
  expect(satelliteArchiveLayer('vegetation','ndre',date,[{...stored[0],has_cog:false}],[]).stored).toBe(false);
  expect(satelliteArchiveLayer('vegetation','ndvi',date,[],[{datetime:date}]).stored).toBe(true);
});
it('shows archived natural colour at full opacity only when the RGB product exists', () => {
  const rgb = [{ date, indices:['truecolor'],has_cog:true }];
  expect(satelliteArchiveLayer('truecolor','ndvi',date,rgb,[])).toEqual({stored:true,index:'truecolor',opacity:1,segment:'tiles'});
  expect(satelliteArchiveLayer('truecolor','ndvi',date,stored,[{datetime:date}]).opacity).toBe(0);
});
