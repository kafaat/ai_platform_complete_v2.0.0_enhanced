import { FeatureDisabledState, ErrorState } from '../StateViews';
import { DegradedState } from './DegradedState';
import type { PageId } from '../../App';

export const AVAILABILITY_STATUS_CODES = [502, 503, 504] as const;
export const PERMISSION_STATUS_CODES = [401, 403] as const;

export function apiStatus(error: unknown): number | undefined {
  return (error as { response?: { status?: number } } | null | undefined)?.response?.status;
}

export function isFeatureDisabledError(error: unknown): boolean {
  return apiStatus(error) === 404;
}

export function isAvailabilityError(error: unknown): boolean {
  const status = apiStatus(error);
  return status != null && AVAILABILITY_STATUS_CODES.includes(status as 502 | 503 | 504);
}

export function isPermissionError(error: unknown): boolean {
  const status = apiStatus(error);
  return status != null && PERMISSION_STATUS_CODES.includes(status as 401 | 403);
}

export function AdvancedServiceState({
  page,
  error,
  resourceName,
  onRetry,
  availableActions = ['متابعة العمل بما هو متاح في الصفحة', 'استخدام آخر بيانات محفوظة إن وُجدت', 'إعادة المحاولة بعد عودة الخدمة'],
}: {
  page: PageId;
  error: unknown;
  resourceName: string;
  onRetry?: () => void;
  availableActions?: string[];
}) {
  if (isFeatureDisabledError(error)) {
    return <FeatureDisabledState page={page} />;
  }

  if (isAvailabilityError(error)) {
    return (
      <DegradedState
        title={`تعمل ${resourceName} في وضع متدهور`}
        detail="الخدمة الخلفية أو قاعدة البيانات غير متاحة حالياً. لا تُعرَض أرقام مُلفَّقة، وسيبقى ما لا يتوفر في حالة فارغة صادقة."
        availableActions={availableActions}
        onRetry={onRetry}
      />
    );
  }

  if (isPermissionError(error)) {
    return (
      <ErrorState
        title="لا تملك صلاحيّة عرض هذه البيانات"
        detail="الخادم رفض الطلب بصلاحيّات المستخدم الحالي. راجع الدور أو المستأجِر قبل إعادة المحاولة."
      />
    );
  }

  return (
    <ErrorState
      title={`تعذّر جلب ${resourceName}`}
      detail="حدث خطأ غير متوقع. لا تعرض الواجهة بيانات بديلة مُخترعة؛ أعد المحاولة أو راجع السجلات."
      onRetry={onRetry}
    />
  );
}
