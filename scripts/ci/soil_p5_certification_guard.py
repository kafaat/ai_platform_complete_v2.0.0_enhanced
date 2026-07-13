from pathlib import Path
root=Path(__file__).resolve().parents[2]
checks={
 'migrations/v165_soil_p5_validation_calibration_certification.sql':['soil_field_validations','soil_regional_calibrations','soil_production_certifications','soil_learning_datasets','FORCE ROW LEVEL SECURITY','WITH CHECK'],
 'services/soil-service/p5_certification.py':['build_learning_manifest','evaluate_promotion','dual_certification_required','lineage_incomplete'],
 'services/soil-service/routers/p5_certification.py':['/soil/validations','/soil/calibrations/build','/soil/production-certifications','/soil/learning-datasets'],
 'services/soil-service/test_soil_p5_certification.py':['test_calibration_and_promotion','test_certification_fail_closed_and_dual_approval']}
for f,need in checks.items():
 s=(root/f).read_text()
 for token in need:
  assert token in s,f'{f}: missing {token}'
print('soil_p5_certification_guard_ok')
