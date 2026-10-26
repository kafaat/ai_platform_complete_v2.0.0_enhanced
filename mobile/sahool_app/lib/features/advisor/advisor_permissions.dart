// SAHOOL — features/advisor/advisor_permissions.dart
// صلاحيّات المستشار كما يفرضها الخادم (services/sahool-platform/core/authorization.py).
// طبقة تجربة فقط: الخادم يرفض بـ403 مهما عرضت الواجهة.
import 'package:sahool_app/core/permissions/permissions.dart';

/// recommendation:request — طلب توصية لحقل، تفاصيل توصية مُخزَّنة، والتغذية الراجعة.
/// (مالك/مدير/مهندس؛ العامل والمشاهد يقرآن عمود الحقل فقط).
const Set<AppRole> kRecommendationRequestRoles = {
  AppRole.owner,
  AppRole.manager,
  AppRole.agronomist,
};

/// pesticide:approve — تدفّق تصعيد الآفة (مالك/مهندس).
const Set<AppRole> kPestEscalationRoles = {AppRole.owner, AppRole.agronomist};

bool canRequestRecommendation(String? role) =>
    kRecommendationRequestRoles.contains(normalizeRole(role));

bool canRunPestEscalation(String? role) =>
    kPestEscalationRoles.contains(normalizeRole(role));
