import type { DrawFeature, DrawFeatureKind, DrawWorkflow } from '../drawingTypes';
import { validateDrawFeature } from '../drawingValidation';
import { validateTopology, type TopologyValidationOptions } from '../topologyValidation';

export interface AgriculturalWorkflowPolicy {
  workflow: DrawWorkflow;
  kind: DrawFeatureKind;
  labelAr: string;
  requiresFieldId: boolean;
  requiresSeasonId: boolean;
  requiresSourceLayer: boolean;
  allowOverlap: boolean;
  requireInsideParent: boolean;
  auditEvent: string;
}

export const AGRICULTURAL_WORKFLOW_POLICIES: Record<DrawWorkflow, AgriculturalWorkflowPolicy> = {
  'create-field': {
    workflow: 'create-field', kind: 'field', labelAr: 'إنشاء حقل', requiresFieldId: false, requiresSeasonId: false,
    requiresSourceLayer: false, allowOverlap: false, requireInsideParent: false, auditEvent: 'FIELD_GEOMETRY_DRAFTED',
  },
  'design-pivot': {
    workflow: 'design-pivot', kind: 'pivot', labelAr: 'تصميم Pivot', requiresFieldId: true, requiresSeasonId: false,
    requiresSourceLayer: false, allowOverlap: true, requireInsideParent: true, auditEvent: 'PIVOT_GEOMETRY_DRAFTED',
  },
  'split-field': {
    workflow: 'split-field', kind: 'field', labelAr: 'تقسيم حقل', requiresFieldId: true, requiresSeasonId: false,
    requiresSourceLayer: false, allowOverlap: false, requireInsideParent: true, auditEvent: 'FIELD_SPLIT_DRAFTED',
  },
  'merge-fields': {
    workflow: 'merge-fields', kind: 'field', labelAr: 'دمج حقول', requiresFieldId: false, requiresSeasonId: false,
    requiresSourceLayer: false, allowOverlap: true, requireInsideParent: false, auditEvent: 'FIELD_MERGE_DRAFTED',
  },
  'create-management-zone': {
    workflow: 'create-management-zone', kind: 'management-zone', labelAr: 'منطقة إدارة', requiresFieldId: true, requiresSeasonId: true,
    requiresSourceLayer: true, allowOverlap: false, requireInsideParent: true, auditEvent: 'MANAGEMENT_ZONE_DRAFTED',
  },
  'create-prescription-zone': {
    workflow: 'create-prescription-zone', kind: 'prescription-zone', labelAr: 'منطقة وصفة', requiresFieldId: true, requiresSeasonId: true,
    requiresSourceLayer: true, allowOverlap: false, requireInsideParent: true, auditEvent: 'PRESCRIPTION_ZONE_DRAFTED',
  },
  'create-exclusion-zone': {
    workflow: 'create-exclusion-zone', kind: 'exclusion-zone', labelAr: 'منطقة استبعاد', requiresFieldId: true, requiresSeasonId: false,
    requiresSourceLayer: false, allowOverlap: true, requireInsideParent: true, auditEvent: 'EXCLUSION_ZONE_DRAFTED',
  },
  'measure-area': {
    workflow: 'measure-area', kind: 'measurement', labelAr: 'قياس مساحة', requiresFieldId: false, requiresSeasonId: false,
    requiresSourceLayer: false, allowOverlap: true, requireInsideParent: false, auditEvent: 'MEASUREMENT_AREA_CREATED',
  },
  'measure-distance': {
    workflow: 'measure-distance', kind: 'path', labelAr: 'قياس مسافة', requiresFieldId: false, requiresSeasonId: false,
    requiresSourceLayer: false, allowOverlap: true, requireInsideParent: false, auditEvent: 'MEASUREMENT_DISTANCE_CREATED',
  },
};

export interface WorkflowCommitCheck {
  canCommit: boolean;
  errors: string[];
  warnings: string[];
  auditEvent: string;
}

export function getWorkflowPolicy(workflow: DrawWorkflow): AgriculturalWorkflowPolicy {
  return AGRICULTURAL_WORKFLOW_POLICIES[workflow];
}

export function applyWorkflowDefaults(feature: DrawFeature, workflow: DrawWorkflow): DrawFeature {
  const policy = getWorkflowPolicy(workflow);
  return {
    ...feature,
    kind: policy.kind,
    properties: {
      ...feature.properties,
      workflow,
      agriculturalWorkflow: policy.labelAr,
      auditEvent: policy.auditEvent,
    },
    updatedAt: new Date().toISOString(),
  };
}

export function checkWorkflowCommit(
  feature: DrawFeature,
  workflow: DrawWorkflow,
  topology: TopologyValidationOptions = {},
): WorkflowCommitCheck {
  const policy = getWorkflowPolicy(workflow);
  const normalized = applyWorkflowDefaults(feature, workflow);
  const geometry = validateDrawFeature(normalized);
  const topo = validateTopology(normalized, {
    ...topology,
    allowOverlap: policy.allowOverlap,
    requireInsideParent: policy.requireInsideParent,
  });
  const errors: string[] = [];
  const warnings: string[] = [];

  if (policy.requiresFieldId && !normalized.properties.fieldId) errors.push('fieldId مطلوب لهذا المسار.');
  if (policy.requiresSeasonId && !normalized.properties.seasonId) errors.push('seasonId مطلوب لهذا المسار.');
  if (policy.requiresSourceLayer && !normalized.properties.sourceLayer) warnings.push('sourceLayer مفضل لتوثيق مصدر منطقة الإدارة/الوصفة.');
  for (const item of [...geometry.issues, ...topo.issues]) {
    if (item.severity === 'error') errors.push(item.message);
    if (item.severity === 'warning') warnings.push(item.message);
  }
  return { canCommit: errors.length === 0, errors, warnings, auditEvent: policy.auditEvent };
}
