// SAHOOL — features/maps/io/presentation/export_screen.dart
// تصدير حدود الحقول كـGeoJSON أو KML ومشاركتها (share_plus): حقل واحد أو الكلّ.
// الهندسة كما أعادها الخادم بكلّ أجزائها وثقوبها؛ الحقل بلا حدود محفوظة يُعلَن
// كذلك ولا يُصدَّر له شيء مختلَق.
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:share_plus/share_plus.dart';

import '../data/maps_io_api.dart';
import '../geo/boundary_writer.dart';
import '../geo/import_model.dart';

/// مُرسِل الملفّ (قابل للاستبدال في الاختبارات).
typedef ShareSink = Future<void> Function(ExportFile file);

Future<void> shareExportFile(ExportFile f) async {
  await Share.shareXFiles(
    [
      XFile.fromData(
        Uint8List.fromList(utf8.encode(f.content)),
        mimeType: f.mimeType,
        name: f.fileName,
      ),
    ],
    fileNameOverrides: [f.fileName],
    subject: f.fileName,
  );
}

sealed class ExportState {
  const ExportState();
}

class ExportLoading extends ExportState {
  const ExportLoading();
}

class ExportFailed extends ExportState {
  const ExportFailed(this.error);
  final Object error;
}

class ExportLoaded extends ExportState {
  const ExportLoaded(this.boundaries, this.withoutGeometry);
  final List<ExportBoundary> boundaries;

  /// أسماء الحقول التي لا تحمل هندسة صالحة من الخادم.
  final List<String> withoutGeometry;
}

class ExportCubit extends Cubit<ExportState> {
  ExportCubit(this._api, {this.onlyFieldId}) : super(const ExportLoading());
  final MapsIoApi _api;
  final String? onlyFieldId;

  Future<void> load() async {
    emit(const ExportLoading());
    try {
      final rows = await _api.listFields();
      final out = <ExportBoundary>[];
      final missing = <String>[];
      for (final f in rows) {
        final id = (f['field_id'] ?? f['id'] ?? '').toString();
        if (onlyFieldId != null && id != onlyFieldId) continue;
        final b = ExportBoundary.fromField(f);
        if (b == null) {
          missing.add((f['name'] ?? id).toString());
        } else {
          out.add(b);
        }
      }
      if (!isClosed) emit(ExportLoaded(out, missing));
    } catch (e) {
      if (!isClosed) emit(ExportFailed(e));
    }
  }
}

class ExportScreen extends StatelessWidget {
  const ExportScreen({super.key, this.api, this.fieldId, this.share});
  final MapsIoApi? api;
  final String? fieldId;
  final ShareSink? share;

  @override
  Widget build(BuildContext context) => BlocProvider(
    create: (_) =>
        ExportCubit(api ?? MapsIoApi.instance, onlyFieldId: fieldId)..load(),
    child: _ExportView(share: share ?? shareExportFile),
  );
}

class _ExportView extends StatefulWidget {
  const _ExportView({required this.share});
  final ShareSink share;

  @override
  State<_ExportView> createState() => _ExportViewState();
}

class _ExportViewState extends State<_ExportView> {
  bool _busy = false;

  Future<void> _export(
    List<ExportBoundary> items,
    BoundaryFormat format,
    String baseName,
  ) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      await widget.share(buildExport(items, format, baseName: baseName));
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('تعذّرت المشاركة: $e')));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      title: 'تصدير حدود الحقول',
      body: BlocBuilder<ExportCubit, ExportState>(
        builder: (context, s) => switch (s) {
          ExportLoading() => const LoadingState(message: 'جارٍ تحميل الحقول'),
          ExportFailed(:final error) => ErrorState(
            error: error,
            onRetry: context.read<ExportCubit>().load,
          ),
          ExportLoaded(:final boundaries, :final withoutGeometry) => _list(
            context,
            boundaries,
            withoutGeometry,
          ),
        },
      ),
    );
  }

  Widget _list(
    BuildContext context,
    List<ExportBoundary> items,
    List<String> missing,
  ) {
    if (items.isEmpty) {
      return EmptyState(
        icon: Icons.layers_clear_outlined,
        title: 'لا حدود للتصدير',
        message: missing.isEmpty
            ? 'لا توجد حقول بعد.'
            : 'الحقول الموجودة بلا حدود محفوظة: ${missing.join('، ')}.',
      );
    }
    return ListView(
      padding: const EdgeInsets.all(SahoolSpacing.page),
      children: [
        if (items.length > 1)
          SectionCard(
            title: 'كلّ الحقول (${items.length})',
            icon: Icons.select_all_rounded,
            child: _FormatButtons(
              enabled: !_busy,
              onPick: (f) => _export(items, f, 'sahool_fields'),
            ),
          ),
        for (final b in items)
          Padding(
            padding: const EdgeInsets.only(top: SahoolSpacing.md),
            child: SectionCard(
              title: b.name,
              icon: Icons.crop_square_rounded,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    '${fmtArea(b.areaHa, decimals: 2)} · '
                    '${b.polygons.length > 1 ? '${b.polygons.length} أجزاء' : 'جزء واحد'}',
                    style: context.textStyles.bodyMedium?.copyWith(
                      color: context.tokens.muted,
                    ),
                  ),
                  const SizedBox(height: SahoolSpacing.sm),
                  _FormatButtons(
                    enabled: !_busy,
                    onPick: (f) => _export([b], f, b.name),
                  ),
                ],
              ),
            ),
          ),
        if (missing.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: SahoolSpacing.md),
            child: StatusChip(
              label: 'بلا حدود محفوظة (لا تُصدَّر): ${missing.join('، ')}',
              tone: StatusTone.info,
            ),
          ),
      ],
    );
  }
}

class _FormatButtons extends StatelessWidget {
  const _FormatButtons({required this.enabled, required this.onPick});
  final bool enabled;
  final ValueChanged<BoundaryFormat> onPick;

  @override
  Widget build(BuildContext context) => Row(
    children: [
      Expanded(
        child: SecondaryButton(
          label: 'GeoJSON',
          icon: Icons.ios_share_rounded,
          onPressed: enabled ? () => onPick(BoundaryFormat.geojson) : null,
        ),
      ),
      const SizedBox(width: SahoolSpacing.sm),
      Expanded(
        child: SecondaryButton(
          label: 'KML',
          icon: Icons.ios_share_rounded,
          onPressed: enabled ? () => onPick(BoundaryFormat.kml) : null,
        ),
      ),
    ],
  );
}
