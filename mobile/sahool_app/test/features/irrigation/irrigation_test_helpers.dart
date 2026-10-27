// أدوات مشتركة لاختبارات الريّ: عميل HTTP مزيّف حقيقيّ (ApiClient نفسه)،
// مضيف واجهة عربيّ RTL، وصندوق إرسال مزيّف يسجّل ما أُودِع.
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:sahool_app/core/theme/app_theme.dart';
import 'package:sahool_app/features/irrigation/data/irrigation_api.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';

import '../../core/fake_http.dart';

export '../../core/fake_http.dart';

class IrrigationHarness {
  IrrigationHarness(FakeHandler handler) : adapter = FakeAdapter(handler) {
    api = IrrigationApi(testClient(adapter, tokens));
  }

  final FakeAdapter adapter;
  final MemoryTokenStore tokens = MemoryTokenStore(
    accessToken: fakeJwt(const Duration(hours: 1)),
  );
  late final IrrigationApi api;

  List<RecordedRequest> posts(String path) => adapter.requests
      .where((r) => r.method == 'POST' && r.path == path)
      .toList();
}

Map<String, dynamic> bodyOf(RecordedRequest r) {
  final d = r.data;
  if (d is Map) return Map<String, dynamic>.from(d);
  if (d is String && d.isNotEmpty) {
    return Map<String, dynamic>.from(jsonDecode(d) as Map);
  }
  return const {};
}

Widget host(Widget child) => MaterialApp(
  theme: AppTheme.light,
  locale: const Locale('ar'),
  supportedLocales: const [Locale('ar'), Locale('en')],
  localizationsDelegates: GlobalMaterialLocalizations.delegates,
  home: child,
);

class FakeOutbox implements OfflineOutbox {
  FakeOutbox({this.accept = true});
  final bool accept;
  final List<OutboxOp> ops = [];

  @override
  Future<OutboxReceipt> enqueue(OutboxOp op) async {
    ops.add(op);
    return accept
        ? const OutboxReceipt.queued()
        : const OutboxReceipt.notQueued('offline_queue_unavailable');
  }

  @override
  Stream<int> get pendingCount => Stream<int>.value(ops.length);
}

const FakeReply connectionDown = FakeReply.fail(
  DioExceptionType.connectionError,
);
