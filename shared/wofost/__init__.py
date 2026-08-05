"""حزمة WOFOST المملوكة — بيت المحرّك النظامي.

أُغلقت شريحة WOFOST Runtime Closure: كان المحرّك في ``wofost_real/`` خارج
سياق Docker (يُنسَخ ``shared/`` فقط)، فحمّله الموجِّه ديناميكيّاً
(``spec_from_file_location``) وعاد ``available: False`` صامتاً في الإنتاج.
الآن يُستورَد استيراداً عاديّاً: ``from shared.wofost import simulate_wofost``.
"""

from shared.wofost.engine import simulate_wofost

__all__ = ["simulate_wofost"]
