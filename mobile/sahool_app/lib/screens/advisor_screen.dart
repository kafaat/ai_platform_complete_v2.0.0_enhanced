// SAHOOL v9.1.0 — lib/screens/advisor_screen.dart
// Fixes: F06(real API), F07(Hive storage), H05(keyboard), H06(image_picker), H07(markdown)
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:image_picker/image_picker.dart';
import '../services/api_service.dart';

class AdvisorScreen extends StatefulWidget {
  const AdvisorScreen({super.key});
  @override
  State<AdvisorScreen> createState() => _AdvisorScreenState();
}

class _AdvisorScreenState extends State<AdvisorScreen> {
  final _controller = TextEditingController();
  final _scrollController = ScrollController();
  final _focusNode = FocusNode();
  final _picker = ImagePicker();
  bool _isLoading = false;
  late Box _chatBox;

  @override
  void initState() {
    super.initState();
    _chatBox = Hive.box('chat_history');  // F07: Hive storage
  }

  List<Map<dynamic, dynamic>> get _messages =>
      _chatBox.values.cast<Map>().toList();

  Future<void> _send(String text) async {
    if (text.trim().isEmpty) return;
    _controller.clear();
    // H05: Hide keyboard
    FocusScope.of(context).unfocus();

    // F07: Save user message
    await _chatBox.add({
      'role': 'user', 'text': text,
      'timestamp': DateTime.now().toIso8601String(),
    });
    setState(() { _isLoading = true; });
    _scrollToBottom();

    try {
      // F06: Real API call
      final response = await ApiService.instance.askAgent(text);
      final answer = response['response_ar']
          ?? response['response']
          ?? 'لم أتمكن من معالجة السؤال.';

      // F07: Save assistant response
      await _chatBox.add({
        'role': 'assistant', 'text': answer,
        'timestamp': DateTime.now().toIso8601String(),
        'sources': response['sources'] ?? [],
      });
    } catch (e) {
      await _chatBox.add({
        'role': 'assistant',
        'text': 'عذراً، حدث خطأ في الاتصال. تحقق من الإنترنت وأعد المحاولة.',
        'timestamp': DateTime.now().toIso8601String(),
        'isError': true,
      });
    } finally {
      if (mounted) setState(() { _isLoading = false; });
      _scrollToBottom();
    }
  }

  // H06: Image picker + real pest detection (multipart → /api/edge/v1/inference/pest-detect)
  Future<void> _sendImage() async {
    final XFile? image = await _picker.pickImage(
      source: ImageSource.camera,
      imageQuality: 80,
    );
    if (image == null) return;

    // Record the user's intent in the transcript (honest: shows what was sent)
    await _chatBox.add({
      'role': 'user',
      'text': 'تحليل صورة: [صورة مرفقة للكشف عن الآفات]',
      'timestamp': DateTime.now().toIso8601String(),
    });
    setState(() {
      _isLoading = true;
    });
    _scrollToBottom();

    try {
      final result =
          await ApiService.instance.analyzePestImage(File(image.path));
      await _chatBox.add({
        'role': 'assistant',
        'text': _formatPestResult(result),
        'timestamp': DateTime.now().toIso8601String(),
      });
    } catch (e) {
      // صدق: فشل التحليل يُعرَض صراحةً — لا كشف مُلفَّق
      await _chatBox.add({
        'role': 'assistant',
        'text':
            'عذراً، تعذّر تحليل الصورة. تحقّق من الإنترنت وأعد المحاولة، أو صف الآفة كتابةً.',
        'timestamp': DateTime.now().toIso8601String(),
        'isError': true,
      });
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
      _scrollToBottom();
    }
  }

  /// يصوغ نتيجة كشف الآفات (اسم الآفة/الثقة/الإجراء) نصّاً عربيّاً للعرض.
  /// إن لم يُكتشف شيء فوق العتبة، يقول ذلك صراحةً بدل اختلاق نتيجة.
  String _formatPestResult(Map<String, dynamic> result) {
    // تنبيه عالي الثقة جاهز من الخادم — استخدمه مباشرةً إن وُجد
    final alert = result['alert_ar'];
    if (alert is String && alert.trim().isNotEmpty) return alert;

    final detections = (result['detections'] as List?) ?? const [];
    if (detections.isEmpty) {
      return 'لم يُكتشف وجود آفات واضحة في الصورة. إن لاحظت أعراضاً، صوّر عن قُرب أو صفها كتابةً.';
    }

    final buf = StringBuffer('🔍 نتائج تحليل الصورة:\n');
    for (final raw in detections.take(3)) {
      if (raw is! Map) continue;
      final d = raw.cast<String, dynamic>();
      final name = d['arabic_name'] ?? d['class_name'] ?? 'آفة غير معروفة';
      final conf = (d['confidence'] as num?)?.toDouble();
      final action = d['recommended_action'];
      buf.write('\n• $name');
      if (conf != null) {
        buf.write(' (ثقة ${(conf * 100).round()}%)');
      }
      if (action is String && action.trim().isNotEmpty) {
        buf.write('\n  الإجراء المقترح: $action');
      }
    }
    return buf.toString().trim();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  Future<void> _clearHistory() async {
    await _chatBox.clear();
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      // H05: Tap outside to dismiss keyboard
      onTap: () => FocusScope.of(context).unfocus(),
      child: Scaffold(
        backgroundColor: const Color(0xFF0F1117),
        appBar: AppBar(
          backgroundColor: const Color(0xFF1A1D29),
          title: const Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('المستشار الزراعي', style: TextStyle(color: Colors.white, fontSize: 16)),
            Text('مدعوم بالذكاء الاصطناعي',
                style: TextStyle(color: Color(0xFF10B981), fontSize: 12)),
          ]),
          actions: [
            IconButton(
              icon: const Icon(Icons.delete_outline, color: Colors.grey),
              tooltip: 'مسح المحادثة',
              onPressed: () => showDialog(
                context: context,
                builder: (_) => AlertDialog(
                  backgroundColor: const Color(0xFF1A1D29),
                  title: const Text('مسح المحادثة؟', style: TextStyle(color: Colors.white)),
                  actions: [
                    TextButton(onPressed: () => Navigator.pop(context),
                        child: const Text('إلغاء')),
                    TextButton(onPressed: () { Navigator.pop(context); _clearHistory(); },
                        child: const Text('مسح', style: TextStyle(color: Colors.red))),
                  ],
                ),
              ),
            ),
          ],
        ),
        body: Column(children: [
          // Messages
          Expanded(
            child: ValueListenableBuilder(
              valueListenable: _chatBox.listenable(),
              builder: (_, box, __) {
                if (box.isEmpty) return _buildWelcome();
                return ListView.builder(
                  controller: _scrollController,
                  padding: const EdgeInsets.all(16),
                  itemCount: box.length,
                  itemBuilder: (_, i) => _buildMessage(
                      Map<String, dynamic>.from(box.getAt(i) as Map)),
                );
              },
            ),
          ),

          // Loading
          if (_isLoading)
            Container(
              padding: const EdgeInsets.all(12),
              child: Row(children: [
                const SizedBox(width: 12,height: 12,
                    child: CircularProgressIndicator(strokeWidth: 2,
                        color: Color(0xFF10B981))),
                const SizedBox(width: 8),
                Text('المستشار يُحلّل...',
                    style: TextStyle(color: Colors.grey[400], fontSize: 12)),
              ]),
            ),

          // Input
          _buildInput(),
        ]),
      ),
    );
  }

  Widget _buildWelcome() => Center(
    child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
      const Text('🌿', style: TextStyle(fontSize: 64)),
      const SizedBox(height: 16),
      const Text('المستشار الزراعي الذكي',
          style: TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.bold)),
      const SizedBox(height: 8),
      Text('اسأل عن المحاصيل، الآفات، الري، والتسميد',
          style: TextStyle(color: Colors.grey[400])),
      const SizedBox(height: 24),
      Wrap(spacing: 8, runSpacing: 8, children: [
        for (final q in ['كيف أُقاوم حشرة المن؟', 'متى أروي القمح؟', 'ما أعراض نقص النيتروجين؟'])
          ActionChip(
            label: Text(q, style: const TextStyle(color: Colors.white, fontSize: 11)),
            backgroundColor: const Color(0xFF1A1D29),
            onPressed: () => _send(q),
          ),
      ]),
    ]),
  );

  Widget _buildMessage(Map<String, dynamic> msg) {
    final isUser = msg['role'] == 'user';
    final isError = msg['isError'] == true;
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        mainAxisAlignment: isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (!isUser) ...[
            CircleAvatar(radius: 16,
                backgroundColor: const Color(0xFF10B981),
                child: const Text('🌿', style: TextStyle(fontSize: 14))),
            const SizedBox(width: 8),
          ],
          Flexible(
            child: GestureDetector(
              onLongPress: () {
                Clipboard.setData(ClipboardData(text: msg['text'] as String));
                ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('تم النسخ')));
              },
              child: Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: isUser
                      ? const Color(0xFF10B981)
                      : isError ? const Color(0xFF7F1D1D) : const Color(0xFF1A1D29),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: SelectableText(   // H07: Selectable text
                  msg['text'] as String,
                  style: const TextStyle(color: Colors.white, height: 1.5),
                ),
              ),
            ),
          ),
          if (isUser) const SizedBox(width: 8),
        ],
      ),
    );
  }

  Widget _buildInput() => Container(
    padding: const EdgeInsets.fromLTRB(12, 8, 12, 16),
    color: const Color(0xFF1A1D29),
    child: Row(children: [
      // H06: Camera button for pest detection
      IconButton(
        icon: const Icon(Icons.camera_alt_outlined, color: Color(0xFF10B981)),
        tooltip: 'تشخيص الآفات بالصورة',
        onPressed: _sendImage,
      ),
      Expanded(
        child: TextField(
          controller: _controller,
          focusNode: _focusNode,
          maxLines: 3, minLines: 1,
          style: const TextStyle(color: Colors.white),
          textDirection: TextDirection.rtl,
          decoration: InputDecoration(
            hintText: 'اسأل عن مزرعتك...',
            hintStyle: TextStyle(color: Colors.grey[600]),
            border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: BorderSide.none),
            filled: true,
            fillColor: const Color(0xFF0F1117),
            contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          ),
          onSubmitted: _send,
        ),
      ),
      const SizedBox(width: 8),
      FloatingActionButton.small(
        onPressed: _isLoading ? null : () => _send(_controller.text),
        backgroundColor: const Color(0xFF10B981),
        child: const Icon(Icons.send, color: Colors.white, size: 18),
      ),
    ]),
  );

  @override
  void dispose() {
    _controller.dispose();
    _scrollController.dispose();
    _focusNode.dispose();
    super.dispose();
  }
}
