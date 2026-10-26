# SAHOOL mobile architecture

This is how the Flutter app is organised and how to change it without editing
a file that another feature owns. Read it before you touch `lib/`.

The app is Arabic first and right to left. Its users are Yemeni farmers,
agronomists and farm managers, often outdoors and on a weak network.

## 1. Layout

```
lib/
  main.dart                  app root: init, MaterialApp, AuthGate (pinned, §3)
  core/                      shared foundation. No feature edits it in wave 2.
    network/                 ApiClient (the only Dio), ApiException, IdempotencyKey,
                             response shape guards, in-flight de-dup, cache,
                             ConnectivityStatus
    routing/                 AppRoute/FeatureModule, AppRouter (aggregator),
                             AppShell (bottom navigation), shell destinations,
                             ShellScope, navigator key, honest route pages
    session/                 SessionScope (logout cleanups), AuthState
    theme/                   tokens.dart (the single token file), AppTheme,
                             SahoolTokens extension, ThemeController
    widgets/                 design-system components (barrel: widgets.dart)
    permissions/             AppRole, normalizeRole, canMutate, canManage
    utils/                   formatters (numbers, units, dates, Arabic digits),
                             ids (UUIDv7), jwt
  features/<feature>/
    <feature>_routes.dart    the feature's routes, menu entries, logout cleanup
    data/<feature>_api.dart  the feature's endpoints
    data/...                 the feature's repositories, models, stores
    presentation/...         the feature's screens, widgets, cubits
  services/                  session services (pinned, §3): ApiService facade,
                             AuthService, WebSocketService, PushService, DeviceId
  screens/  widgets/  models/  config/  utils/
                             pinned legacy paths only (§3)
```

There are 18 features. Each one has a routes file and a data API file:

auth · dashboard · farms · fields · satellite · irrigation · tasks · inventory ·
equipment · devices · documents · advisor · master_data · profile ·
operations_hub · more · field_forms · realtime

`test/core/app_router_test.dart` fails if a folder under `lib/features/` has no
`<x>_routes.dart`, is not registered, or has no API file.

## 2. Ownership: the rule that keeps parallel work conflict-free

A feature agent edits only:

- `lib/features/<its feature>/**`
- `test/features/<its feature>/**` (create it)
- the pinned files listed for its feature in §3

Everything else is read-only during wave 2: `lib/core/**`, `main.dart`,
`pubspec.yaml`/`pubspec.lock`, other features, and `analysis_options.yaml`.
If you need a core change, a new dependency or a new menu section, stop and
ask the coordinator. Do not work around it in your own folder by copying core
code.

Other features may import your `data/<x>_api.dart`. These cross-feature reads
exist today:

| Consumer | Uses |
|---|---|
| fields (workspace) | `IrrigationApi.listSchedules`, `SatelliteApi.getFieldIndicators`, `SatelliteApi.getFieldNdviTimeseries` |
| satellite | `DashboardApi.getDashboard` (field list) |
| profile | `AuthApi.logout` |
| core shell | `DashboardApi.getDashboard` (zero-fields check), `OnboardingScreen` |

So public methods of an API class are **append-only** in wave 2. Add new
methods and new optional parameters. Do not rename or remove a method, and do
not change its return shape.

## 3. Pinned paths: files that CI reads by path from outside the app

Gates outside `mobile/` open some app files by path and check their text. These
files cannot move until those gates are updated, and that is outside this
app's ownership. The text listed under "must keep" has to stay.

| Path | Read by | Must keep | Wave-2 owner |
|---|---|---|---|
| `lib/main.dart` | `scripts/ci/mobile_contract_gate.py`, `tests_v9/test_field_forms_mobile_runtime_wiring.py` | `kDebugMode`-guarded error text "يرجى المحاولة مجدداً", `if (!AuthService.instance.isAuthenticated)`, `FieldFormsCoordinator.instance.init()` / `.dispose()` | core (frozen) |
| `lib/services/api_service.dart` | `mobile_contract_gate.py`, `tests/mobile/test_phase11_mobile_offline_sync_runtime.py`, `test_field_forms_mobile_runtime_wiring.py` | `logout` with `finally` + `WebSocketService.instance.dispose()` + `clearCache()`; `/api/v1/sync/manifest`, `/api/v1/sync/status`, `syncOfflineOperations` without a client `tenantId`; `/api/ai-agronomist/chat`; `Dio get dio => _dio` | core; **advisor** owns `askAgent` only |
| `lib/services/websocket_service.dart`, `auth_service.dart`, `device_id_service.dart` | `mobile_contract_gate.py`, `tests_v9/test_roadmap_phase23.py`, `test_field_forms_mobile_runtime_wiring.py` | fail-closed auth frame (`policyViolation`, `missing-auth`), `_messageQueue.clear()`, secure storage, `clearAuth` that keeps the device id | core (frozen) |
| `lib/screens/dashboard_screen.dart` | `tests_v9/test_chatgpt_gap_batch_20261015.py`, `tests_v9/test_mobile_dashboard_reads_no_unproduced_water_fields.py`, `test/dashboard_carbon_not_measured_test.dart` | `CarbonNotMeasuredCard()`, `WaterUsageNotMeasuredCard()`; no read of `carbon`/`water_usage`/`savings_pct` keys | **dashboard** |
| `lib/widgets/carbon_not_measured_card.dart`, `water_usage_card.dart` | same | "غير مقيس" constants | **dashboard** |
| `lib/screens/field_workspace_screen.dart` | `test_field_forms_mobile_runtime_wiring.py` | `FieldFormsCoordinator.instance.syncField(_fieldId)` | **fields** |
| `lib/widgets/offline_field_map.dart` | `mobile_contract_gate.py`, `test_roadmap_phase23.py` | `offlinePackFilePath`, PMTiles → MBTiles → network fallback | **fields** |
| `lib/models/canonical_field_geometry.dart` | `capabilities/registry/capabilities.json`; mirrored by `shared/domain/field_geometry.py` | file exists | **fields** |
| `lib/config/app_config.dart` | `tests_v9/test_mobile_release_build_requires_endpoint_defines.py` | `String.fromEnvironment('API_URL'/'WS_URL', defaultValue: …)` | core (frozen) |
| `lib/features/field_forms/data/field_forms_coordinator.dart`, `field_forms_api.dart` | `test_field_forms_mobile_runtime_wiring.py` | `FieldFormsApi(ApiService.instance.dio)`, `'X-Device-Id': deviceId` | **field_forms** |
| `lib/features/realtime/**` | `config/service_feature_ui_contracts.json` | folder path | **realtime** |
| `test/auth_service_test.dart`, `test/field_forms/condition_corpus_data.dart` | `mobile_contract_gate.py`, `tests_v9/test_field_forms_corpus_mirror_static.py` | the `package:sahool_app/utils/jwt.dart` import; the corpus constant | core / field_forms |

`lib/screens/{equipment,farms,field_create_wizard,fields,inventory,mfa_setup,satellite,tasks}_screen.dart`
and `lib/utils/jwt.dart` are one-line re-exports. They exist because the
capability registry and the contract gate name the old paths. Never add code
to them. Delete them once those pointers move.

Every new Dart file changes `capability_mapping_engine.py --check`
(`.github/workflows/capability-governance.yml`), which scans
`mobile/sahool_app/lib`. Its generated artifacts live outside this app.
Regenerate them once after all wave-2 branches merge, with
`python scripts/ci/capability_mapping_engine.py --generate`, not on each branch,
because 15 branches regenerating the same JSON would conflict.

## 4. Networking: adding an endpoint

Add the endpoint to **your** `features/<x>/data/<x>_api.dart`. Never add it to
`ApiService`.

```dart
class FarmsApi {
  FarmsApi([ApiClient? client]) : _client = client ?? ApiClient.instance;
  static final FarmsApi instance = FarmsApi();
  final ApiClient _client;

  Future<Map<String, dynamic>> getFarm(String id) async =>
      asJsonMap(await _client.get('/api/v1/farms/$id'));

  Future<Map<String, dynamic>> updateFarm(String id, Map<String, dynamic> body,
          {IdempotencyKey? idempotencyKey}) async =>
      asJsonMap(await _client.patch('/api/v1/farms/$id',
          data: body, idempotencyKey: idempotencyKey));
}
```

- `ApiClient` handles the base URL, bearer token, `X-Request-ID`, token
  refresh and bounded retry. Do not create another `Dio`. Field forms and
  realtime use `ApiClient.instance.dio` (through `ApiService.instance.dio`)
  when they need raw Dio.
- Every failure arrives as `ApiException` with a `kind` (`network`, `timeout`,
  `unauthorized`, `forbidden`, `notFound`, `conflict`, `validation`,
  `unavailable`, `server`, …) and an honest Arabic `messageAr`. Display it with
  `ErrorState(error: e)` or `apiErrorMessage(e)`. The 503, 401, 403 and 404
  wording is a contract, so don't replace it with generic text.
- Shape guards: `asJsonMap`, `asJsonList` and `asWrappedJsonList(data, ['items'])`
  throw `FormatException` on a wrong shape. A wrong shape is an error, never an
  empty list.
- **Writes and idempotency.** Create one `IdempotencyKey.generate()` per user
  intent, for example when the add sheet opens, and pass the same key on every
  submit of that intent. A write is retried on 502/503/504 only when it carries
  a key. Without a key it is never retried, so a lost response cannot create a
  second irrigation record or ledger entry. Do not generate a key per call.
  The server must also honour the key on that endpoint; check the handler
  before you rely on it.
- Slow calls take `receiveTimeout` and `sendTimeout` per call through
  `send(...)` (the advisor uses 120 s). Multipart bodies are never retried.
- Call `send(..., authenticated: false)` only for pre-login endpoints.
- Use `ResponseCache` and `InFlight` (see `DashboardApi`) when several screens
  read the same resource.
- Never invent data. A missing value is shown as `kNotMeasured` ("غير مقيس"),
  never as 0, "null" or a plausible guess. No mock data in `lib/`.

## 5. Routing: adding a screen, a menu entry or a deep link

Add an `AppRoute` to **your** `<x>_routes.dart`:

```dart
AppRoute(
  path: '/farms/detail',                 // the canonical name and deep link
  titleAr: 'تفاصيل المزرعة',
  icon: Icons.agriculture_outlined,
  allowedRoles: RouteRoles.editors,      // null = any signed-in role
  menu: const MenuEntry(MenuSection.farm, order: 20), // optional: shows in «المزيد»
  builder: (context, args) => FarmDetailScreen(farmId: args['farm_id']),
),
```

- Navigate with `context.openRoute('/farms/detail?farm_id=f1')` or with
  `Navigator.pushNamed`. `args['k']` reads the query string first, then a
  `Map` passed as `arguments`. `args.extra` is the raw `arguments`.
- Paths are unique across the app. A duplicate throws at start-up and fails
  `app_router_test`. Use your feature's prefix.
- `allowedRoles` shows an honest "no permission" page. It is a UX layer only;
  the server enforces RBAC.
- The More screen and the operations hub are built from `menu:` entries. Do
  not edit `more_screen.dart` to add your feature. `MenuSection` is in core and
  adding a section is a coordinator change.
- Bottom navigation (`core/routing/shell_destinations.dart`) is fixed:
  الرئيسية `/dashboard`, الحقول `/fields`, المهام `/tasks`, المستشار `/advisor`,
  المزيد `/more`. Viewers have no Tasks tab, and workers open on Tasks. A tab's
  content is its feature's route builder. To switch tabs from inside a tab,
  use `ShellScope.maybeOf(context)?.select('fields')`.
- Tabs are built lazily and kept alive. Hidden tabs run under
  `HeroMode(false)`. For a FAB in a pushed screen, use `AppFab(heroKey: ...)`.
- Logout cleanup: set `onSessionEnd:` on your `FeatureModule` to clear Hive
  boxes, caches or queues that belong to the user. It runs on explicit logout,
  before tokens are cleared, and receives the ending `tenantId` and `userId`.
  Do not delete unsent field work. Filter it by tenant instead, as
  `SubmissionQueue.pending(tenantId:)` does.

## 6. Design system

- **Tokens** live in `core/theme/tokens.dart` only: `SahoolColors.light`/`.dark`,
  the status ramp, `ndviColor()`, `SahoolSpacing` (4/8/12/16/24/32),
  `SahoolRadius` (8/12/16/pill), `SahoolType` (12/14/16/20/28; 400/600/700;
  line height 1.5) and `SahoolSizes.minTouchTarget = 48`. Do not add
  `Color(0x…)` literals in new code.
- In widgets, read `Theme.of(context).colorScheme`, `context.tokens.muted`,
  `.line`, `.success`, `.warning`, `.danger`, `.info`, and
  `context.textStyles.titleMedium` and similar.
- **Contrast** is tested: text and actions are at least 4.5:1 in both themes
  (`test/core/theme_tokens_test.dart`). The light primary is `#2E7D32`; brand
  green `#3EB050` is for status and accents, not white-text buttons.
- **Components** (`import 'package:sahool_app/core/widgets/widgets.dart';`):
  `AppScaffold`, `AppFab`, `SectionCard`, `MetricTile` (null shows
  "غير مقيس"), `StatusChip` (colour plus icon plus text, never colour
  alone), `LoadingState`, `ErrorState(error:, onRetry:)`, `EmptyState`,
  `PrimaryButton` (52 dp, `loading` blocks a second submit), `SecondaryButton`,
  `AppIconButton` (requires a tooltip), `AppTextField`, `AppNumberField`,
  `AppDropdown`, `AppListTile`, `ListSectionHeader`, `OpsTile` (list row with
  status chips under the text), `OpsDateField` (date picker field),
  `OpsRefreshBanner` ("refresh failed" over the last data), `showAppBottomSheet`
  with `AppSheet` (inline `errorText`; a SnackBar raised from a sheet is drawn
  under it), `showConfirmDialog`, and the app-wide offline banner (already
  mounted in `MaterialApp.builder`).
- **RTL**: use `EdgeInsetsDirectional` and `AlignmentDirectional`, and
  `start`/`end` instead of `left`/`right`. Directional icons such as
  `chevron_right` mirror automatically.
- **Numbers**: parse every user number with `parseLocalizedNum`, or use
  `AppNumberField`/`LocalizedDigitsFormatter`. Arabic keyboards type ٠-٩ and
  ٫, and `double.tryParse('٢٫٥')` returns null. Display with `fmtArea`,
  `fmtMm`, `fmtTempC`, `fmtPct`, `fmtYieldKgHa`, `fmtYer`, `fmtDate` and
  `fmtDateTime`. These use Western digits, matching the web, and Arabic units
  هـ, مم, °م, كجم/هـ, ٪ and ر.ي. Dates are converted with `toLocal()`.
- **Theme mode**: light and dark both exist. The default is dark for now
  (`ThemeController.defaultMode`), because the moved screens still hard-code
  dark surfaces (`kBg`, `kSurface` and white text). Under the light theme,
  their inputs would show white text on a light fill. When you migrate a
  screen, replace `kBg`/`kSurface`/`kPrimary`/`Colors.white*` with theme
  reads. Once every screen has migrated, the coordinator flips the default to
  `ThemeMode.light`, which reads better in sunlight.
- **Font**: the system Arabic font for now (`SahoolType.fontFamily = null`).
  Cairo is OFL licensed but its `.ttf` files are not in the repo. Bundling it
  is a coordinator change (assets and pubspec).

## 7. State management

Use `flutter_bloc` with **one cubit per screen or flow, inside the feature**:

```
features/farms/presentation/
  farms_cubit.dart     // class FarmsCubit extends Cubit<FarmsState>
  farms_state.dart     // sealed: FarmsLoading | FarmsLoaded(list) | FarmsFailed(ApiException)
  farms_screen.dart    // BlocProvider(create: (_) => FarmsCubit(FarmsApi.instance)..load())
```

- The cubit takes its API class in its constructor, which makes it testable
  with a fake `ApiClient`. Screens never call `ApiClient` directly.
- States are explicit and honest: loading, loaded, empty, and failed holding
  the `ApiException`. Do not show a stale value as current. If you show cached
  data, show its age with `fmtAge`.
- Provide the cubit in the route builder or the screen, not at app root.
  `main.dart` provides no feature blocs.
  (`features/dashboard/presentation/dashboard_bloc.dart` exists but nothing
  consumes it yet; the dashboard owner decides whether to keep it.)
- Many screens still use `setState` with direct API calls. Convert them when
  you redesign the screen; no big-bang rewrite.

## 8. Session, auth and realtime events

- `AuthGate` (in `main.dart`) loads the session. When the access token has
  expired but a refresh token remains, it refreshes once before deciding. It
  listens to `AuthState` (sign-in and sign-out) and to
  `ApiClient.onSessionExpired`, so a rejected refresh token returns the user
  to login from any screen.
- After login call `AuthState.instance.signedIn()`. After logout call
  `AuthApi.instance.logout()` and then `AuthState.instance.signedOut()`. Never
  push a new `AuthGate`.
- `ApiService.logout`, in this order: unregister the push token, then
  `/auth/logout`, with a 10 s cap on both. Then, always: dispose the
  WebSocket, clear the cache, run `SessionScope` cleanups, clear the tokens.
- WebSocket events: `WebSocketService.instance.on('alert').listen(...)`
  delivers typed `WsEvent`s. The socket reconnects with a refreshed token when
  the app resumes or the network returns. The server currently handles only
  `ping`, so `send()` commands are not executed server-side; do not build UI
  that assumes they are.

## 9. Tests

- Run them with `flutter test`, and run `flutter analyze` too. CI blocks on
  errors only (`--no-fatal-infos --no-fatal-warnings`). Add no new warnings.
- Put feature tests in `test/features/<x>/`. Core tests are in `test/core/`.
- For networking tests, use `test/core/fake_http.dart`: `FakeAdapter` records
  requests and replies through a function; it works with
  `testClient(adapter, MemoryTokenStore(...))` and `fakeJwt(...)`. Pass the
  client to your API class (`FarmsApi(client)`) and assert on the real
  requests, headers included. Do not re-implement production logic inside a
  test.
- For widget tests, pump a `MaterialApp` with `AppTheme.light`, Arabic
  `locale`, and `GlobalMaterialLocalizations.delegates`. Without the delegates
  every TextField throws. For honesty tests, assert that a missing value
  renders "غير مقيس" and that 503/403 render their messages.
- A guard test must fail when its guard is removed. Check that once before
  you rely on it.

## 10. Known gaps after the foundation pass

These are not fixed here; each one names its owner.

- **dashboard**: render from the producer's real shape (`kpis[]`,
  `fields_summary`, alerts `title_ar`/`message_ar`/`alert_id`) and subscribe
  to `WsEvent` alerts.
- **advisor**: read `answer_ar`/`message`/`evidence_sources`. `askAgent` now
  also sends `question`. Require a field before pest detection, and scope or
  encrypt `chat_history`, which is cleared on logout today.
- **field_forms**: stamp the actor on queued items, freeze `submitted_at` at
  enqueue, serialise screen sync and coordinator drain, and show poison items
  instead of deleting them.
- **wave-2 screens**: replace the 14 deprecated `value:`/`activeColor:` uses,
  migrate the screens to tokens, and pass `IdempotencyKey` on writes.
- **coordinator** (outside `mobile/`): update the capability registry
  pointers and the gate paths in §3, regenerate the capability mapping, then
  delete the re-export shims. A debug-only Android `network_security_config`
  for `10.0.2.2`, deriving `WS_URL` from `API_URL`, and app-link intent
  filters for deep links are also still open.
