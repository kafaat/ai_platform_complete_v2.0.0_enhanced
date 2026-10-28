// جدولة إعادة المحاولة المشتركة بين صفّي المزامنة: Retry-After بصيغتيه، وbackoff
// أُسّيّ محدود بـjitter لا يتجاوز ٢٠٪، وتقريب المؤقّت إلى الثانية التالية.
import 'dart:io' show HttpDate;
import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/retry_schedule.dart';

class _FixedRandom implements Random {
  _FixedRandom(this.value);
  final double value;
  @override
  double nextDouble() => value;
  @override
  int nextInt(int max) => 0;
  @override
  bool nextBool() => false;
}

void main() {
  final now = DateTime.utc(2026, 10, 28, 12);

  group('parseRetryAfter', () {
    test('missing, blank or unparseable values yield null', () {
      for (final raw in [null, '', '   ', 'soon', '1.5']) {
        expect(parseRetryAfter(raw, now: now), isNull, reason: '$raw');
      }
    });

    test('delta-seconds are read, surrounding whitespace ignored', () {
      expect(parseRetryAfter('0', now: now), Duration.zero);
      expect(parseRetryAfter(' 120 ', now: now), const Duration(seconds: 120));
    });

    test('a negative delta is refused rather than scheduled in the past', () {
      expect(parseRetryAfter('-5', now: now), isNull);
    });

    test('an HTTP date in the future becomes the remaining wait', () {
      final at = now.add(const Duration(minutes: 3));
      expect(
        parseRetryAfter(HttpDate.format(at), now: now),
        const Duration(minutes: 3),
      );
    });

    test('an HTTP date already past means retry now, not a negative wait', () {
      final at = now.subtract(const Duration(hours: 1));
      expect(parseRetryAfter(HttpDate.format(at), now: now), Duration.zero);
    });

    test('a non-UTC clock is normalised before comparing with the date', () {
      final at = now.add(const Duration(seconds: 30));
      expect(
        parseRetryAfter(HttpDate.format(at), now: now.toLocal()),
        const Duration(seconds: 30),
      );
    });

    test('absurd server values are capped so the queue never freezes', () {
      expect(parseRetryAfter('999999999', now: now), kMaxRetryAfter);
      final far = now.add(const Duration(days: 365));
      expect(parseRetryAfter(HttpDate.format(far), now: now), kMaxRetryAfter);
      expect(
        parseRetryAfter('600', now: now, max: const Duration(minutes: 5)),
        const Duration(minutes: 5),
      );
    });
  });

  group('retryBackoff', () {
    const base = Duration(seconds: 2);
    const max = Duration(minutes: 5);

    test('doubles per attempt from the base, without jitter at zero', () {
      final r = _FixedRandom(0);
      final waits = [
        for (final n in [0, 1, 2, 3, 4])
          retryBackoff(n, base: base, max: max, random: r).inSeconds,
      ];
      expect(waits, [2, 2, 4, 8, 16]);
    });

    test('is capped at max, and jitter adds at most 20 percent on top', () {
      final low = retryBackoff(
        30,
        base: base,
        max: max,
        random: _FixedRandom(0),
      );
      final high = retryBackoff(
        30,
        base: base,
        max: max,
        random: _FixedRandom(0.999999),
      );
      expect(low, max);
      expect(high.inMilliseconds, lessThanOrEqualTo(max.inMilliseconds * 1.2));
      expect(high, greaterThan(max));
    });

    test('a huge attempt count neither overflows nor goes negative', () {
      for (final n in [21, 63, 64, 1000, 1 << 30]) {
        final d = retryBackoff(
          n,
          base: base,
          max: max,
          random: _FixedRandom(0),
        );
        expect(d, max, reason: 'attempts=$n');
      }
    });

    test('with a real Random every wait stays inside [capped, capped*1.2]', () {
      final random = Random(1298);
      for (var n = 1; n <= 12; n++) {
        final capped = min(
          base.inMilliseconds * (1 << (n - 1)),
          max.inMilliseconds,
        );
        final d = retryBackoff(n, base: base, max: max, random: random);
        expect(
          d.inMilliseconds,
          inInclusiveRange(capped, (capped * 1.2).round()),
        );
      }
    });
  });

  group('ceilToSecond', () {
    test('zero or negative waits still arm a one-second timer', () {
      expect(ceilToSecond(Duration.zero), const Duration(seconds: 1));
      expect(
        ceilToSecond(const Duration(seconds: -3)),
        const Duration(seconds: 1),
      );
    });

    test('rounds up so the timer never fires before the due time', () {
      expect(
        ceilToSecond(const Duration(milliseconds: 1)),
        const Duration(seconds: 1),
      );
      expect(
        ceilToSecond(const Duration(milliseconds: 1001)),
        const Duration(seconds: 2),
      );
      expect(
        ceilToSecond(const Duration(seconds: 7)),
        const Duration(seconds: 7),
      );
    });
  });
}
