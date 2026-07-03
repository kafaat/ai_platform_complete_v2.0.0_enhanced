import { describe, expect, it } from 'vitest';
import { readFieldIdFromSearch, resolveFieldViewSelection, writeFieldIdToSearch } from './fields';

const options = [{ id: 'north' }, { id: 'south' }];

describe('FieldView selection resolver', () => {
  it('prefers a valid route field over stored selection', () => {
    expect(resolveFieldViewSelection({ options, storedFieldId: 'north', routeFieldId: 'south' })).toEqual({
      fieldId: 'south',
      reason: 'route',
      routeFieldIsInvalid: false,
      storedFieldIsInvalid: false,
    });
  });

  it('falls back to stored selection when route field is invalid', () => {
    expect(resolveFieldViewSelection({ options, storedFieldId: 'north', routeFieldId: 'missing' })).toEqual({
      fieldId: 'north',
      reason: 'stored',
      routeFieldIsInvalid: true,
      storedFieldIsInvalid: false,
    });
  });

  it('falls back deterministically when stored field is stale', () => {
    expect(resolveFieldViewSelection({ options, storedFieldId: 'deleted' })).toEqual({
      fieldId: 'north',
      reason: 'fallback',
      routeFieldIsInvalid: false,
      storedFieldIsInvalid: true,
    });
  });

  it('returns an honest empty state without fields', () => {
    expect(resolveFieldViewSelection({ options: [], storedFieldId: 'deleted', routeFieldId: 'ghost' })).toEqual({
      fieldId: '',
      reason: 'empty',
      routeFieldIsInvalid: true,
      storedFieldIsInvalid: true,
    });
  });

  it('normalizes deep-link query keys to field_id', () => {
    expect(readFieldIdFromSearch('?fieldId=abc&x=1')).toBe('abc');
    expect(writeFieldIdToSearch('?fieldId=abc&x=1', 'north')).toBe('?x=1&field_id=north');
  });
});
