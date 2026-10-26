// SAHOOL — features/maps/draw/field_created_events.dart
// إشارة «أُنشئ حقل» للشاشات المحفوظة في الذاكرة (تبويب «الحقول» يبقى حيّاً في
// الغلاف، فلا يُعيد التحميل حين يُفتح المعالج من مكانٍ آخر كالإعداد الأوّل).
// يكفي المشترك أن يستمع ويعيد التحميل:
//   FieldCreatedEvents.instance.stream.listen((_) => _load());
import 'dart:async';

class FieldCreatedEvents {
  FieldCreatedEvents._();
  static final FieldCreatedEvents instance = FieldCreatedEvents._();

  final StreamController<Map<String, dynamic>> _c =
      StreamController<Map<String, dynamic>>.broadcast();

  /// كلّ حقل يُنشأ بنجاح (استجابة الخادم كما هي).
  Stream<Map<String, dynamic>> get stream => _c.stream;

  void notifyCreated(Map<String, dynamic> field) => _c.add(field);
}
