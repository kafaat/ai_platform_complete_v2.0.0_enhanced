/// SAHOOL mobile endpoint policy.
///
/// Production defaults are HTTPS/WSS. Local emulator URLs are allowed only when
/// building with --dart-define=SAHOOL_ENV=dev.
class AppConfig {
  static const env = String.fromEnvironment('SAHOOL_ENV', defaultValue: 'prod');
  static const apiUrl = String.fromEnvironment('API_URL', defaultValue: 'https://api.sahool.ye');
  static const wsUrl = String.fromEnvironment('WS_URL', defaultValue: 'wss://api.sahool.ye');

  static const _localHosts = ['localhost', '127.0.0.1', '0.0.0.0', '10.0.2.2'];

  static bool get isDev => env == 'dev';

  static Uri get apiUri => _checkedUri('API_URL', apiUrl, allowedSchemes: const ['https', 'http']);
  static Uri get wsUri => _checkedUri('WS_URL', wsUrl, allowedSchemes: const ['wss', 'ws']);

  static Uri _checkedUri(String name, String value, {required List<String> allowedSchemes}) {
    final uri = Uri.parse(value);
    if (!uri.hasScheme || !allowedSchemes.contains(uri.scheme)) {
      throw StateError('$name must use one of: ${allowedSchemes.join(', ')}');
    }
    final host = uri.host.toLowerCase();
    if (!isDev && _localHosts.contains(host)) {
      throw StateError('$name points to local host $host while SAHOOL_ENV=$env. Use SAHOOL_ENV=dev for emulator/local runs.');
    }
    if (!isDev && (uri.scheme == 'http' || uri.scheme == 'ws')) {
      throw StateError('$name must use HTTPS/WSS unless SAHOOL_ENV=dev. Current value: $value');
    }
    return uri;
  }
}
