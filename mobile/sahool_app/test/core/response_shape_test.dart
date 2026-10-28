// حرّاس شكل الاستجابة: عقدٌ تغيّر أو صفحة HTML من وسيط تُرمى FormatException صريحة
// ولا تُبتلَع كقائمة فارغة توحي بـ«لا بيانات».
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/response_shape.dart';

void main() {
  group('asJsonList', () {
    test('accepts a list of objects and keeps their content', () {
      final rows = asJsonList([
        {'id': 1},
        {'id': 2, 'name': 'حقل'},
      ]);
      expect(rows, [
        {'id': 1},
        {'id': 2, 'name': 'حقل'},
      ]);
      expect(rows.first, isA<Map<String, dynamic>>());
    });

    test('an empty list is a real empty result, not an error', () {
      expect(asJsonList(<dynamic>[]), isEmpty);
    });

    test('a proxy HTML page, null, or an object is refused', () {
      for (final data in [
        '<!doctype html><html></html>',
        null,
        {'items': []},
        3,
      ]) {
        expect(() => asJsonList(data), throwsFormatException, reason: '$data');
      }
    });

    test('one non-object element rejects the whole list', () {
      expect(
        () => asJsonList([
          {'id': 1},
          'oops',
        ]),
        throwsFormatException,
      );
      expect(() => asJsonList([null]), throwsFormatException);
    });
  });

  group('asJsonMap', () {
    test('accepts an object', () {
      expect(asJsonMap({'ok': true}), {'ok': true});
    });

    test('refuses a list, a string or null', () {
      for (final data in [<dynamic>[], 'text', null]) {
        expect(() => asJsonMap(data), throwsFormatException, reason: '$data');
      }
    });
  });

  group('asWrappedJsonList', () {
    test('accepts a bare list', () {
      expect(
        asWrappedJsonList(
          [
            {'id': 1},
          ],
          ['tasks'],
        ),
        [
          {'id': 1},
        ],
      );
    });

    test('unwraps the first listed key that holds a list', () {
      final data = {
        'meta': {'page': 1},
        'tasks': [
          {'id': 'a'},
        ],
        'items': [
          {'id': 'b'},
        ],
      };
      expect(asWrappedJsonList(data, ['tasks', 'items']), [
        {'id': 'a'},
      ]);
      expect(asWrappedJsonList(data, ['missing', 'items']), [
        {'id': 'b'},
      ]);
    });

    test('a wrapper key holding a non-list is skipped, not trusted', () {
      final data = {
        'tasks': {'id': 'not-a-list'},
        'items': [
          {'id': 'b'},
        ],
      };
      expect(asWrappedJsonList(data, ['tasks', 'items']), [
        {'id': 'b'},
      ]);
    });

    test('an object with none of the keys is refused, not read as empty', () {
      expect(
        () => asWrappedJsonList({'data': []}, ['tasks']),
        throwsFormatException,
      );
    });

    test('a bad element inside the wrapped list is still refused', () {
      expect(
        () => asWrappedJsonList(
          {
            'tasks': [1, 2],
          },
          ['tasks'],
        ),
        throwsFormatException,
      );
    });
  });
}
