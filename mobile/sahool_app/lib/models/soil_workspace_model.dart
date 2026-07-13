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

  factory SoilWorkspaceModel.fromJson(Map<String,dynamic> json) => SoilWorkspaceModel(
    profileHash: json['profile_hash'] ?? '', evidenceLevel: json['evidence_level'] ?? 'baseline_only',
    completenessPct: (json['completeness_pct'] ?? 0).toDouble(),
    conflicts: List<String>.from(json['conflicts'] ?? const []), allowedUse: List<String>.from(json['allowed_use'] ?? const []),
    blockedUse: List<String>.from(json['blocked_use'] ?? const []), historyCount: json['history_count'] ?? 0,
    pendingApprovals: json['pending_approvals'] ?? 0,
  );

  String blockedReason(String action) => blockedUse.contains(action)
      ? 'Blocked until the required soil evidence and approval are available'
      : '';
}
