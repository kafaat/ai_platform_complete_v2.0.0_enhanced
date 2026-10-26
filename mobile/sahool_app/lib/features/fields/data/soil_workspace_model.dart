class SoilWorkspaceModel {
  final String profileHash;
  final String evidenceLevel;
  final double completenessPct;
  final List<String> conflicts;
  final List<String> allowedUse;
  final List<String> blockedUse;
  final int historyCount;
  final int pendingApprovals;

  const SoilWorkspaceModel({required this.profileHash, required this.evidenceLevel, required this.completenessPct, required this.conflicts, required this.allowedUse, required this.blockedUse, required this.historyCount, required this.pendingApprovals});

  /// تحليل مُنمَّط: نوع غير متوقّع لحقلٍ ما يسقط إلى قيمته الافتراضيّة بدل أن
  /// ينهار التحويل الضمنيّ من dynamic (كانت 8 تحويلات ضمنيّة هنا).
  factory SoilWorkspaceModel.fromJson(Map<String, dynamic> json) {
    String str(String k, String fallback) {
      final v = json[k];
      return v is String ? v : fallback;
    }

    int integer(String k) {
      final v = json[k];
      return v is num ? v.toInt() : 0;
    }

    List<String> strings(String k) {
      final v = json[k];
      return v is Iterable ? v.whereType<String>().toList() : const <String>[];
    }

    final pct = json['completeness_pct'];
    return SoilWorkspaceModel(
      profileHash: str('profile_hash', ''),
      evidenceLevel: str('evidence_level', 'baseline_only'),
      completenessPct: pct is num ? pct.toDouble() : 0,
      conflicts: strings('conflicts'),
      allowedUse: strings('allowed_use'),
      blockedUse: strings('blocked_use'),
      historyCount: integer('history_count'),
      pendingApprovals: integer('pending_approvals'),
    );
  }

  String blockedReason(String action) => blockedUse.contains(action)
      ? 'Blocked until the required soil evidence and approval are available'
      : '';
}
