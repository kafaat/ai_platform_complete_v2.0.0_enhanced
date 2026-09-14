# Build the mobile app

Use Flutter **3.27.4 / Dart 3.6.2**, Java 17, and the committed `pubspec.lock`.
Android uses Gradle 8.7 / Android Gradle Plugin 8.6.1 and minSdk 23. iOS requires
macOS, Xcode, CocoaPods, and iOS 13 or later. Android and iOS projects are generated
from the official Flutter 3.27.4 templates and adapted for the actual plugins.

```bash
flutter pub get --enforce-lockfile
flutter analyze
flutter test
flutter build apk --debug --no-pub
```

CI builds an Android debug APK in addition to analysis/tests. A debug build is
not a signed store release. Android release signing is deliberately unconfigured;
set the operator's release keystore through the normal Gradle signing mechanism.
For iOS, select the registered bundle identifier, signing team and provisioning
profile in Xcode before a signed device/archive build.

The generated identifiers are `com.sahool.sahool_app` (Android) and
`com.sahool.sahoolApp` (iOS). Register these exact identifiers in your Firebase
project, or update the native identifiers to the existing provisioned app before
supplying its configuration. Place real files at:

- `android/app/google-services.json`
- `ios/Runner/GoogleService-Info.plist`

These files and signing material are excluded from git. Builds can omit Firebase
configuration; push then remains dormant. Android applies Google Services only
when the real file exists; the iOS build copies its plist when supplied. The iOS
entitlement uses `APS_ENVIRONMENT` from the Debug/Release xcconfig. Enable Push
Notifications for the registered App ID and configure the real APNs credentials
in Firebase. No synthetic provider configuration or signing keys are shipped.

Camera, location, notification, and biometric permissions are declared for the
existing features. Requests remain subject to OS/user permission. Android uses
`FlutterFragmentActivity` and an AppCompat launch theme for `local_auth`.

Endpoint configuration uses the existing `API_URL`, `WS_URL` and `SAHOOL_ENV`
Dart defines; production requires HTTPS/WSS. Local HTTP is only appropriate for
an explicit development build and a corresponding debug network configuration.

The September 13 local validation includes Flutter analysis and all 80 Flutter
tests. Android SDK/Xcode builds, a signed install, background notification delivery
and a real FCM/APNs receipt on a handset still require their respective runners
and provisioned accounts; source analysis does not certify them.
