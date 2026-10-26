// Legacy path kept only as a pointer. The real code lives in
// lib/features/inventory/presentation/inventory_screen.dart. This path is still referenced from outside the app
// (capabilities/registry/capabilities.json and
// docs/capability-registry/domains/*.yaml), and
// tests/architecture/test_capability_traceability.py requires every pointer
// there to exist. Do not add code here. Delete this file once those pointers
// are moved to the new path. See ARCHITECTURE.md, "Pinned paths".
export 'package:sahool_app/features/inventory/presentation/inventory_screen.dart';
