// قراءة ردّ المستشار من مفاتيح الخادم الحقيقيّة — answer_ar لا response_ar.
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/features/advisor/data/advisor_models.dart';

import 'advisor_test_helpers.dart';

void main() {
  test('reads answer_ar, evidence_sources and the uncalibrated flag', () {
    final r = AdvisorReply.fromJson(chatReply(answer: 'جواب الأدلّة'));
    expect(r.answerAr, 'جواب الأدلّة');
    expect(r.confidence, 0.42);
    expect(r.confidenceCalibrated, isFalse);
    expect(r.evidenceSources.map((s) => s.labelAr), ['RAG', 'Knowledge Graph']);
    expect(r.evidenceSources.last.available, isFalse);
    expect(r.requiresHumanReview, isTrue);
    expect(r.limitations, ['generation_disabled_evidence_only']);
  });

  test(
    'the legacy response_ar key is not read (it never existed server-side)',
    () {
      expect(
        () => AdvisorReply.fromJson({'response_ar': 'x', 'response': 'y'}),
        throwsFormatException,
      );
    },
  );

  test('falls back to `message` (the server mirrors answer_ar there)', () {
    expect(AdvisorReply.fromJson({'message': 'm'}).answerAr, 'm');
  });

  test('claims are shown only when the server verified them', () {
    final claims = {
      'claims': [
        {'path': '/soil/ph', 'value': 7.2, 'product_digest': 'd'},
      ],
    };
    final verified = AdvisorReply.fromJson(
      chatReply(validation: {'status': 'verified', ...claims}),
    );
    expect(verified.claims.single.path, '/soil/ph');
    expect(verified.claims.single.value, '7.2');

    final blocked = AdvisorReply.fromJson(
      chatReply(validation: {'status': 'blocked', ...claims}),
    );
    expect(blocked.claims, isEmpty);
  });

  test('missing confidence stays null (never 0)', () {
    final json = chatReply()..remove('confidence');
    expect(AdvisorReply.fromJson(json).confidence, isNull);
  });

  test('blocked_by_policy is labelled honestly', () {
    final r = AdvisorReply.fromJson(
      chatReply(generationStatus: GenerationStatus.blockedByPolicy),
    );
    expect(r.blockedByPolicy, isTrue);
    expect(generationStatusLabel(r.generationStatus), contains('سياسة'));
  });

  test('a stored entry round-trips through the history map', () {
    final reply = AdvisorReply.fromJson(
      chatReply(
        validation: {
          'status': 'verified',
          'claims': [
            {'path': '/a', 'value': 1},
          ],
        },
      ),
    );
    final entry = ChatEntry(
      role: ChatRole.assistant,
      text: reply.answerAr,
      at: DateTime.utc(2026, 10, 26, 9),
      reply: reply,
      fieldId: 'f-1',
    );
    final back = ChatEntry.fromMap(entry.toMap())!;
    expect(back.reply!.confidenceCalibrated, isFalse);
    expect(back.reply!.claims.single.path, '/a');
    expect(back.reply!.evidenceSources, hasLength(2));
    expect(back.fieldId, 'f-1');
  });

  test('field recommendations keep server text and nulls', () {
    final set = FieldRecommendationSet.fromJson({
      'field_id': 'f',
      'weather_available': false,
      'requires_review': true,
      'field_state': {
        'validity': 'partial',
        'reasons_ar': ['لا حسّاس'],
      },
      'recommendations': [
        {
          'category': 'fertilizer',
          'priority': 'high',
          'title_ar': 'سمّد',
          'detail_ar': 'تفصيل',
          'source': 'heuristic',
          'safety': false,
        },
      ],
    }, 'f');
    expect(set.items.single.titleAr, 'سمّد');
    expect(set.weatherAvailable, isFalse);
    expect(set.reasonsAr, ['لا حسّاس']);
    expect(
      () => FieldRecommendationSet.fromJson({}, 'f'),
      throwsFormatException,
    );
  });

  test('engine recommendation without a yield keeps it null', () {
    final rec = EngineRecommendation.fromJson({
      'delivered': true,
      'rec_id': 'r1',
      'recommendation': {'headline': 'اروِ', 'confidence': 'medium'},
    });
    expect(rec.predictedYieldTHa, isNull);
    expect(rec.headline, 'اروِ');
  });
}
