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

  test('citations name the source and link only http(s)', () {
    final r = AdvisorReply.fromJson(chatReply(extra: evidenceGaps()));
    expect(r.citations.map((c) => c.chunkId), ['c1', 'c2', 'c3']);

    final fao = r.citations[0];
    expect(fao.title, 'FAO');
    expect(fao.link, Uri.parse('https://www.fao.org/x'));
    expect(fao.revision, '2021');
    expect(fao.locator, 'Kc · ص 12');

    final upload = r.citations[1];
    expect(upload.title, 'soil report.pdf');
    expect(upload.title, isNot(contains('tenant-7')));
    expect(upload.link, isNull);

    expect(r.citations[2].link, isNull);
    expect(r.unverifiedReferences, 2);
  });

  test(
    'missing evidence, absent references and an unsaved audit are named',
    () {
      final r = AdvisorReply.fromJson(chatReply(extra: evidenceGaps()));
      expect(r.evidenceMissing.map(evidenceMissingLabel), [
        'لا دليل مرجعيّ يسند الإجابة',
        'فجوة معرفة: soil_ec',
        'new_code',
      ]);
      expect(
        r.ragUnavailableText,
        'لا توجد قاعدة معرفة مراجَعة لهذا الحساب بعد',
      );
      expect(r.auditNotPersistedText, 'لم يُحفَظ سجلّ تدقيق لهذه الإجابة.');

      final unconfirmed = AdvisorReply.fromJson(
        chatReply(
          extra: {
            'rag_available': false,
            'rag_unavailable_reason': 'other_code',
            'audit_event': {'status': 'unconfirmed'},
          },
        ),
      );
      expect(unconfirmed.ragUnavailableText, contains('other_code'));
      expect(
        unconfirmed.auditNotPersistedText,
        'لم يتأكّد حفظ سجلّ تدقيق لهذه الإجابة.',
      );
    },
  );

  test('nothing is claimed when the server reports no gap', () {
    final recorded = AdvisorReply.fromJson(
      chatReply(
        extra: {
          'rag_available': true,
          'audit_event': {'status': 'recorded', 'persisted': true},
        },
      ),
    );
    expect(recorded.ragUnavailableText, isNull);
    expect(recorded.auditNotPersistedText, isNull);

    final silent = AdvisorReply.fromJson(chatReply());
    expect(silent.ragUnavailableText, isNull);
    expect(silent.auditNotPersistedText, isNull);
    expect(silent.citations, isEmpty);
    expect(silent.evidenceMissing, isEmpty);
  });

  test('an answer without an advisory envelope still needs human review', () {
    final bare = AdvisorReply.fromJson({'answer_ar': 'x'});
    expect(bare.requiresHumanReview, isNull);
    expect(bare.needsHumanReview, isTrue);

    final exempt = AdvisorReply.fromJson({
      'answer_ar': 'x',
      'advisory': {'requires_human_review': false},
    });
    expect(exempt.needsHumanReview, isFalse);
  });

  test('evidence gaps survive the history round-trip', () {
    final reply = AdvisorReply.fromJson(chatReply(extra: evidenceGaps()));
    final back = AdvisorReply.fromJson(reply.toJson());
    expect(back.citations.map((c) => c.title), ['FAO', 'soil report.pdf', 'X']);
    expect(back.citations.first.locator, 'Kc · ص 12');
    expect(back.unverifiedReferences, 2);
    expect(back.evidenceMissing, reply.evidenceMissing);
    expect(back.ragUnavailableText, reply.ragUnavailableText);
    expect(back.auditNotPersistedText, reply.auditNotPersistedText);
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
