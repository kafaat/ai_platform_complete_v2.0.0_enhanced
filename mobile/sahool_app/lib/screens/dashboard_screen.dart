import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:shimmer/shimmer.dart';

import '../services/api_service.dart';
import '../services/auth_service.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  bool _isLoading = true;
  Map<String, dynamic>? _dashboardData;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadDashboard();
  }

  Future<void> _loadDashboard() async {
    try {
      setState(() => _isLoading = true);

      // ✅ FIXED: Real API call via ApiService

      // النتيجة الحيّة من /indicators/v1/overview تُستعمَل مباشرةً (لا نموذج وهميّ).
      // (كان هنا map معلّق بعد الفاصلة المنقوطة يكسر التصريف — أُزيل.)
      _dashboardData = await ApiService.instance.getDashboard();

      setState(() {
        _isLoading = false;
        _error = null;
      });
    } catch (e) {
      setState(() {
        _isLoading = false;
        _error = e.toString();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    // H04: SafeArea in parent MainNavigation
    if (_isLoading) {
      return const SafeArea(child: Center(child: CircularProgressIndicator()));
    }

    if (_error != null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.error_outline, color: Colors.red, size: 48),
            const SizedBox(height: 16),
            Text('خطأ في تحميل البيانات', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 8),
            Text(_error!, style: Theme.of(context).textTheme.bodyMedium),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: _loadDashboard,
              child: const Text('إعادة المحاولة'),
            ),
          ],
        ),
      );
    }

    final data = _dashboardData!;

    return SafeArea(
      child: RefreshIndicator(
      onRefresh: _loadDashboard,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // ─── Header Stats ─────────────────────────────────
          _buildStatsRow(data),
          const SizedBox(height: 20),

          // ─── NDVI Chart ───────────────────────────────────
          _buildNDVIChart(data['ndvi_history'] as List<dynamic>),
          const SizedBox(height: 20),

          // ─── Weather Card ─────────────────────────────────
          _buildWeatherCard(data['weather_today'] as Map<String, dynamic>),
          const SizedBox(height: 20),

          // ─── Alerts ───────────────────────────────────────
          _buildAlertsSection(data['alerts'] as List<dynamic>),
          const SizedBox(height: 20),

          // ─── Yield Forecast ───────────────────────────────
          _buildYieldForecast(data['yield_forecast'] as Map<String, dynamic>),
          const SizedBox(height: 20),

          // ─── Market Prices ────────────────────────────────
          _buildMarketPrices(data['market_prices'] as Map<String, dynamic>),
          const SizedBox(height: 20),

          // ─── Water & Carbon ───────────────────────────────
          _buildResourceCards(data),
        ],
      ),
    );
  }

  Widget _buildStatsRow(Map<String, dynamic> data) {
    return Row(
      children: [
        Expanded(
          child: _StatCard(
            icon: Icons.agriculture,
            label: 'الحقول',
            value: '${(data['fields_count'] ?? 0)}',
            subtitle: '${data['total_area_ha']} هكتار',
            color: const Color(0xFF10B981),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _StatCard(
            icon: Icons.water_drop,
            label: 'توفير المياه',
            value: '${data['water_usage']['savings_pct']}%',
            subtitle: 'هذا الشهر',
            color: const Color(0xFF3B82F6),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _StatCard(
            icon: Icons.eco,
            label: 'الكربون',
            value: '${data['carbon']['sequestered_kg']}',
            subtitle: 'كجم CO₂',
            color: const Color(0xFF22C55E),
          ),
        ),
      ],
    );
  }

  Widget _buildNDVIChart(List<dynamic> history) {
    final spots = history.asMap().entries.map((e) {
      return FlSpot(e.key.toDouble(), (e.value['value'] as num).toDouble());
    }).toList();

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  'مؤشر NDVI',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                  decoration: BoxDecoration(
                    color: const Color(0xFF10B981).withOpacity(0.2),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(
                    'صحة جيدة',
                    style: TextStyle(
                      color: const Color(0xFF10B981),
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              'متوسط 30 يوم: ${history.last['value']}',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: 16),
            SizedBox(
              height: 200,
              child: LineChart(
                LineChartData(
                  gridData: const FlGridData(show: false),
                  titlesData: FlTitlesData(
                    leftTitles: const AxisTitles(
                      sideTitles: SideTitles(showTitles: true, reservedSize: 40),
                    ),
                    bottomTitles: AxisTitles(
                      sideTitles: SideTitles(
                        showTitles: true,
                        getTitlesWidget: (value, meta) {
                          final idx = value.toInt();
                          if (idx >= 0 && idx < history.length) {
                            final date = history[idx]['date'] as String;
                            return Text(
                              date.substring(5), // MM-DD
                              style: const TextStyle(fontSize: 10, color: Colors.grey),
                            );
                          }
                          return const Text('');
                        },
                        reservedSize: 30,
                      ),
                    ),
                    rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                    topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                  ),
                  borderData: FlBorderData(show: false),
                  minY: 0,
                  maxY: 1,
                  lineBarsData: [
                    LineChartBarData(
                      spots: spots,
                      isCurved: true,
                      color: const Color(0xFF10B981),
                      barWidth: 3,
                      isStrokeCapRound: true,
                      dotData: const FlDotData(show: true),
                      belowBarData: BarAreaData(
                        show: true,
                        color: const Color(0xFF10B981).withOpacity(0.1),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildWeatherCard(Map<String, dynamic> weather) {
    final iconMap = {
      'sunny': Icons.wb_sunny,
      'cloudy': Icons.wb_cloudy,
      'rainy': Icons.water_drop,
      'storm': Icons.thunderstorm,
    };

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  'الطقس اليوم',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                Icon(
                  iconMap[weather['condition']] ?? Icons.wb_sunny,
                  color: const Color(0xFFF59E0B),
                  size: 32,
                ),
              ],
            ),
            const SizedBox(height: 16),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              children: [
                _WeatherItem(
                  icon: Icons.thermostat,
                  label: 'الحرارة',
                  value: '${weather['temp_max']}° / ${weather['temp_min']}°',
                ),
                _WeatherItem(
                  icon: Icons.water_drop_outlined,
                  label: 'الرطوبة',
                  value: '${weather['humidity']}%',
                ),
                _WeatherItem(
                  icon: Icons.air,
                  label: 'الرياح',
                  value: '${weather['wind_speed']} كم/س',
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAlertsSection(List<dynamic> alerts) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'التنبيهات',
          style: Theme.of(context).textTheme.titleLarge,
        ),
        const SizedBox(height: 12),
        ...alerts.map((alert) => _AlertCard(alert: alert as Map<String, dynamic>)),
      ],
    );
  }

  Widget _buildYieldForecast(Map<String, dynamic> forecast) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'توقعات الإنتاجية',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 16),
            ...forecast.entries.map((entry) {
              final crop = entry.key;
              final data = entry.value as Map<String, dynamic>;
              final current = (data['current_kg_ha'] as num).toDouble();
              final predicted = (data['predicted_kg_ha'] as num).toDouble();
              final confidence = (data['confidence'] as num).toDouble();
              final progress = current / predicted;

              return Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text(
                          _cropName(crop),
                          style: const TextStyle(fontWeight: FontWeight.w600),
                        ),
                        Text(
                          '${predicted.toStringAsFixed(0)} كجم/هكتار',
                          style: TextStyle(
                            color: const Color(0xFF10B981),
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    LinearProgressIndicator(
                      value: progress.clamp(0.0, 1.0),
                      backgroundColor: Colors.grey[800],
                      valueColor: AlwaysStoppedAnimation<Color>(
                        confidence > 0.8 ? const Color(0xFF10B981) : const Color(0xFFF59E0B),
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'ثقة: ${(confidence * 100).toStringAsFixed(0)}% | الحالي: ${current.toStringAsFixed(0)}',
                      style: const TextStyle(fontSize: 12, color: Colors.grey),
                    ),
                  ],
                ),
              );
            }),
          ],
        ),
      ),
    );
  }

  Widget _buildMarketPrices(Map<String, dynamic> prices) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  'أسعار السوق',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                TextButton(
                  onPressed: () {},
                  child: const Text('الكل'),
                ),
              ],
            ),
            const SizedBox(height: 12),
            ...prices.entries.map((entry) {
              final crop = entry.key;
              final data = entry.value as Map<String, dynamic>;
              final price = (data['price_yer_kg'] as num).toInt();
              final trend = data['trend'] as String;

              IconData trendIcon;
              Color trendColor;
              if (trend == 'up') {
                trendIcon = Icons.trending_up;
                trendColor = const Color(0xFF10B981);
              } else if (trend == 'down') {
                trendIcon = Icons.trending_down;
                trendColor = const Color(0xFFEF4444);
              } else {
                trendIcon = Icons.trending_flat;
                trendColor = Colors.grey;
              }

              return ListTile(
                leading: CircleAvatar(
                  backgroundColor: const Color(0xFF1A1D29),
                  child: Text(
                    _cropEmoji(crop),
                    style: const TextStyle(fontSize: 20),
                  ),
                ),
                title: Text(_cropName(crop)),
                subtitle: Text('صنعاء — اليوم'),
                trailing: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      '$price ر.ي',
                      style: const TextStyle(
                        fontWeight: FontWeight.bold,
                        fontSize: 16,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Icon(trendIcon, color: trendColor, size: 20),
                  ],
                ),
              );
            }),
          ],
        ),
      ),
    );
  }

  Widget _buildResourceCards(Map<String, dynamic> data) {
    final water = data['water_usage'] as Map<String, dynamic>;
    final carbon = data['carbon'] as Map<String, dynamic>;

    return Row(
      children: [
        Expanded(
          child: Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(Icons.water_drop, color: Color(0xFF3B82F6), size: 28),
                  const SizedBox(height: 12),
                  Text(
                    '${water['this_month_m3']} م³',
                    style: Theme.of(context).textTheme.displayMedium?.copyWith(fontSize: 22),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'استهلاك المياه',
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'توفير ${water['savings_pct']}% عن الشهر الماضي',
                    style: const TextStyle(
                      color: Color(0xFF10B981),
                      fontSize: 12,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(Icons.eco, color: Color(0xFF22C55E), size: 28),
                  const SizedBox(height: 12),
                  Text(
                    '${carbon['sequestered_kg']}',
                    style: Theme.of(context).textTheme.displayMedium?.copyWith(fontSize: 22),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'كجم CO₂ مخزّن',
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '\$${carbon['credit_value_usd']} قيمة اعتماد',
                    style: const TextStyle(
                      color: Color(0xFFF59E0B),
                      fontSize: 12,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildShimmer() {
    return Shimmer.fromColors(
      baseColor: const Color(0xFF1A1D29),
      highlightColor: const Color(0xFF2A2D3A),
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Row(
            children: List.generate(3, (_) => Expanded(
              child: Container(
                height: 100,
                margin: const EdgeInsets.symmetric(horizontal: 4),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(16),
                ),
              ),
            )),
          ),
          const SizedBox(height: 20),
          Container(
            height: 280,
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(16),
            ),
          ),
          const SizedBox(height: 20),
          Container(
            height: 150,
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(16),
            ),
          ),
        ],
      ),
    );
  }

  String _cropName(String crop) {
    final names = {
      'wheat': 'قمح',
      'barley': 'شعير',
      'maize': 'ذرة',
      'millet': 'ذرة بيضاء',
      'rice': 'أرز',
      'tomato': 'طماطم',
      'potato': 'بطاطس',
      'coffee': 'قهوة',
      'qat': 'قات',
    };
    return names[crop] ?? crop;
  }

  String _cropEmoji(String crop) {
    final emojis = {
      'wheat': '🌾',
      'barley': '🌾',
      'maize': '🌽',
      'millet': '🌾',
      'rice': '🍚',
      'tomato': '🍅',
      'potato': '🥔',
      'coffee': '☕',
      'qat': '🌿',
    };
    return emojis[crop] ?? '🌱';
  }
}

// ─── Sub-Widgets ───────────────────────────────────────────

class _StatCard extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final String subtitle;
  final Color color;

  const _StatCard({
    required this.icon,
    required this.label,
    required this.value,
    required this.subtitle,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: color, size: 24),
            const SizedBox(height: 8),
            Text(
              value,
              style: Theme.of(context).textTheme.displayMedium?.copyWith(fontSize: 20),
            ),
            Text(
              label,
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(fontSize: 12),
            ),
            Text(
              subtitle,
              style: const TextStyle(fontSize: 11, color: Colors.grey),
            ),
          ],
        ),
      ),
    );
  }
}

class _WeatherItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;

  const _WeatherItem({
    required this.icon,
    required this.label,
    required this.value,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Icon(icon, color: const Color(0xFF3B82F6), size: 28),
        const SizedBox(height: 4),
        Text(
          value,
          style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
        ),
        Text(
          label,
          style: const TextStyle(fontSize: 12, color: Colors.grey),
        ),
      ],
    );
  }
}

class _AlertCard extends StatelessWidget {
  final Map<String, dynamic> alert;

  const _AlertCard({required this.alert});

  @override
  Widget build(BuildContext context) {
    final severity = alert['severity'] as String;
    final Color severityColor;
    final IconData severityIcon;

    switch (severity) {
      case 'high':
        severityColor = const Color(0xFFEF4444);
        severityIcon = Icons.error;
        break;
      case 'medium':
        severityColor = const Color(0xFFF59E0B);
        severityIcon = Icons.warning;
        break;
      default:
        severityColor = const Color(0xFF3B82F6);
        severityIcon = Icons.info;
    }

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: Icon(severityIcon, color: severityColor),
        title: Text(alert['message'] as String),
        subtitle: Text(
          '${alert['field']} — ${alert['action']}',
          style: const TextStyle(fontSize: 12),
        ),
        trailing: const Icon(Icons.chevron_left),
        onTap: () {
          // Navigate to alert detail
        },
      ),
    ));
  }
    );
}
