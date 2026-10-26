// Legacy path kept only as a pointer. The real code lives in
// lib/core/utils/jwt.dart. scripts/ci/mobile_contract_gate.py requires
// test/auth_service_test.dart to import exactly
// 'package:sahool_app/utils/jwt.dart' (so the test runs the real JWT code
// rather than a copy). Delete this file once that gate names the new path.
// See ARCHITECTURE.md, "Pinned paths".
export 'package:sahool_app/core/utils/jwt.dart';
