// SAHOOL — lib/screens/tasks_screen.dart
// المهام اليومية/الموزّعة في الموبايل: GET /api/v1/tasks + PATCH /api/v1/tasks/{id}.
// لا fallback وهمي: الخطأ يظهر صريحاً. أزرار البدء/الإنجاز مخفية عن viewer.
import 'package:flutter/material.dart';
import '../permissions.dart';
import '../services/api_service.dart';
import '../widgets/state_views.dart';

class TasksScreen extends StatefulWidget {
  const TasksScreen({super.key});
  @override
  State<TasksScreen> createState() => _TasksScreenState();
}

class _TasksScreenState extends State<TasksScreen> {
  late Future<List<Map<String, dynamic>>> _future;
  String _filter = 'all';
  String? _busyTaskId;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<List<Map<String, dynamic>>> _load() => ApiService.instance.fetchTasks();
  void _retry() => setState(() => _future = _load());

  Future<void> _setStatus(String taskId, String status) async {
    setState(() => _busyTaskId = taskId);
    try {
      await ApiService.instance.updateTaskStatus(taskId, status);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(status == 'completed' ? 'تم إنجاز المهمة' : 'تم بدء المهمة')),
      );
      _retry();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(apiErrorMessage(e))),
      );
    } finally {
      if (mounted) setState(() => _busyTaskId = null);
    }
  }

  static const _statusAr = {
    'pending': 'بانتظار التنفيذ',
    'in_progress': 'قيد التنفيذ',
    'completed': 'مُنجزة',
    'cancelled': 'ملغاة',
  };

  static const _typeAr = {
    'irrigation': 'ريّ',
    'fertilization': 'تسميد',
    'spraying': 'رشّ',
    'harvest': 'حصاد',
    'scouting': 'كشف ميدانيّ',
    'soil_sampling': 'عيّنة تربة',
  };

  Color _statusColor(String status) {
    switch (status) {
      case 'completed': return kPrimary;
      case 'in_progress': return kSecondary;
      case 'pending': return kWarn;
      default: return Colors.grey;
    }
  }

  String _text(dynamic v, [String fallback = '—']) {
    final s = v?.toString() ?? '';
    return s.isEmpty ? fallback : s;
  }

  @override
  Widget build(BuildContext context) {
    final mutable = canMutate(currentRole());
    return Scaffold(
      backgroundColor: kBg,
      appBar: AppBar(
        backgroundColor: kSurface,
        title: const Text('المهام اليومية'),
        actions: [
          IconButton(onPressed: _retry, icon: const Icon(Icons.refresh)),
        ],
      ),
      body: FutureBuilder<List<Map<String, dynamic>>>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) return const LoadingView();
          if (snap.hasError) {
            return ErrorView(message: apiErrorMessage(snap.error!), onRetry: _retry);
          }
          final all = snap.data ?? const <Map<String, dynamic>>[];
          final tasks = all.where((t) => _filter == 'all' || _text(t['status'], '') == _filter).toList();
          if (all.isEmpty) {
            return const EmptyView(message: 'لا توجد مهام موزّعة حالياً.', icon: Icons.task_alt);
          }
          return Column(
            children: [
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.all(12),
                child: Row(
                  children: [
                    _FilterChip('الكل', 'all', _filter, (v) => setState(() => _filter = v)),
                    _FilterChip('بانتظار', 'pending', _filter, (v) => setState(() => _filter = v)),
                    _FilterChip('قيد التنفيذ', 'in_progress', _filter, (v) => setState(() => _filter = v)),
                    _FilterChip('مُنجزة', 'completed', _filter, (v) => setState(() => _filter = v)),
                  ],
                ),
              ),
              Expanded(
                child: ListView.separated(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                  itemCount: tasks.length,
                  separatorBuilder: (_, __) => const SizedBox(height: 10),
                  itemBuilder: (_, i) {
                    final t = tasks[i];
                    final id = _text(t['task_id'] ?? t['id'], '');
                    final status = _text(t['status'], 'pending');
                    final type = _text(t['task_type'], 'scouting');
                    final busy = _busyTaskId == id;
                    return Container(
                      decoration: BoxDecoration(
                        color: kSurface,
                        borderRadius: BorderRadius.circular(14),
                        border: Border.all(color: Colors.white10),
                      ),
                      padding: const EdgeInsets.all(14),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Row(
                            children: [
                              Icon(Icons.assignment_outlined, color: _statusColor(status)),
                              const SizedBox(width: 8),
                              Expanded(
                                child: Text(_typeAr[type] ?? type,
                                    style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                              ),
                              _StatusPill(_statusAr[status] ?? status, _statusColor(status)),
                            ],
                          ),
                          const SizedBox(height: 8),
                          Text(_text(t['field_name'] ?? t['field_id']),
                              style: const TextStyle(color: Colors.white70, fontSize: 12)),
                          if (_text(t['notes'], '').isNotEmpty)
                            Padding(
                              padding: const EdgeInsets.only(top: 6),
                              child: Text(_text(t['notes'], ''),
                                  style: const TextStyle(color: Colors.grey, fontSize: 12)),
                            ),
                          const SizedBox(height: 8),
                          Wrap(
                            spacing: 12,
                            runSpacing: 6,
                            children: [
                              _Meta(Icons.calendar_today, _text(t['recommended_date'])),
                              _Meta(Icons.timer_outlined, '${_text(t['estimated_duration_min'], '—')} دقيقة'),
                              _Meta(Icons.attach_money, _text(t['estimated_cost_usd'])),
                            ],
                          ),
                          if (mutable && id.isNotEmpty && status != 'completed' && status != 'cancelled') ...[
                            const SizedBox(height: 12),
                            Row(
                              children: [
                                if (status == 'pending')
                                  Expanded(
                                    child: OutlinedButton(
                                      onPressed: busy ? null : () => _setStatus(id, 'in_progress'),
                                      child: const Text('بدء'),
                                    ),
                                  ),
                                if (status == 'pending') const SizedBox(width: 8),
                                Expanded(
                                  child: ElevatedButton(
                                    onPressed: busy ? null : () => _setStatus(id, 'completed'),
                                    style: ElevatedButton.styleFrom(backgroundColor: kPrimary),
                                    child: busy
                                        ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                                        : const Text('إنجاز'),
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ],
                      ),
                    );
                  },
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _FilterChip extends StatelessWidget {
  final String label;
  final String value;
  final String current;
  final ValueChanged<String> onSelect;
  const _FilterChip(this.label, this.value, this.current, this.onSelect);
  @override
  Widget build(BuildContext context) {
    final active = value == current;
    return Padding(
      padding: const EdgeInsetsDirectional.only(end: 8),
      child: ChoiceChip(
        label: Text(label),
        selected: active,
        onSelected: (_) => onSelect(value),
        selectedColor: kPrimary,
        backgroundColor: kSurface,
        labelStyle: TextStyle(color: active ? Colors.white : Colors.white70),
      ),
    );
  }
}

class _StatusPill extends StatelessWidget {
  final String label;
  final Color color;
  const _StatusPill(this.label, this.color);
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
    decoration: BoxDecoration(
      color: color.withOpacity(0.12),
      borderRadius: BorderRadius.circular(999),
      border: Border.all(color: color.withOpacity(0.4)),
    ),
    child: Text(label, style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.w600)),
  );
}

class _Meta extends StatelessWidget {
  final IconData icon;
  final String text;
  const _Meta(this.icon, this.text);
  @override
  Widget build(BuildContext context) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      Icon(icon, size: 13, color: Colors.grey),
      const SizedBox(width: 4),
      Text(text, style: const TextStyle(color: Colors.grey, fontSize: 11)),
    ],
  );
}
