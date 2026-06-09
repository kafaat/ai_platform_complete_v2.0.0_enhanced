#!/usr/bin/env python3
"""
Hierarchical Intent Router for SAHOOL Supervisor Agent
Classifies queries into domains and sub-intents for skill routing.
"""

import re


class HierarchicalRouter:
    """
    Two-level routing:
    Level 1: Domain (remote_sensing, crop_model, market, advisory)
    Level 2: Sub-intent (ndvi, irrigation, pest, price, etc.)
    """

    def __init__(self, skill_libraries: dict):
        self.skill_libraries = skill_libraries

        # Domain keywords (Arabic + English)
        self.domain_patterns = {
            "remote_sensing": [
                r"ndvi|ندفي|صحة.*حقل|صورة.*فضائية|satellite|sentinel|أقمار|خرائط",
                r"لون|green|red|nir|swir|radar|رادار|sar",
            ],
            "crop_model": [
                r"wofost|محاكاة|نموذج|yield|إنتاج|biomass|كتلة.*حيوية|gdd|phenology",
                r"irrigation|ري|أسقي|اسقي|سقي|مياه|et0|evapotranspiration|تبخير|fertilizer|تسميد|npk",
            ],
            "market": [
                r"price|سعر|market|سوق|buy|buyer|buyers|buying|sell|seller|selling|بيع|شراء|contract|عقد",
                r"carbon|كربون|credit|ائتمان|subsidy|إعانة|loan|قرض",
            ],
            "advisory": [
                r"pest|آفة|disease|مرض|weed|أعشاب|advice|نصيحة|recommend|توصية|what.*do|ماذا.*أفعل",
                r"help|مساعدة|problem|مشكلة|symptom|عرض|damage|ضرر|treatment|علاج",
            ],
        }

        self.sub_intent_patterns = {
            "remote_sensing": {
                "ndvi": r"ndvi|ندفي|vegetation_index|مؤشر.*نبات",
                "full_analysis": r"full.*analysis|تحليل.*شامل|complete.*report|تقرير.*كامل",
                "change_detection": r"change|تغير|difference|فرق|compare|مقارنة|before.*after|قبل.*بعد",
            },
            "crop_model": {
                "simulate_current": r"simulate|محاكاة|model|نموذج|predict|تنبؤ|forecast|توقع",
                "irrigation_advice": r"irrigation|ري|أسقي|اسقي|سقي|مياه|water.*need|حاجة.*مياه|when.*water|متى.*أسقي|schedule|جدول",
                "fertilizer_advice": r"fertilizer|تسميد|npk|nutrient|غذائ|feed|أطعم|when.*fertilize|متى.*أسمد",
            },
            "market": {
                "price_current": r"price|سعر|cost|تكلفة|how.*much|كم.*سعر",
                "price_forecast": r"forecast|توقع|future|مستقبل|trend|اتجاه|will.*price|هل.*يرتفع|next.*month|الشهر.*القادمة",
                "create_contract": r"contract|عقد|sell.*before|بيع.*قبل|forward|آجل|pre.*harvest|قبل.*الحصاد|buyer|مشتري",
            },
            "advisory": {
                "pest_id": r"pest|آفة|insect|حشرة|bug|بق|worm|دودة|identify|تشخيص|what.*this|ما.*هذا|photo.*pest|صورة.*آفة",
                "disease_id": r"disease|مرض|fungus|فطر|virus|فيروس|bacteria|بكتيريا|spot|بقعة|rot|تعفن|wilt|ذبول",
                "general_advice": r"advice|نصيحة|recommend|توصية|suggest|أقترح|what.*do|ماذا.*أفعل|how.*improve|كيف.*أحسن|best.*practice|أفضل.*ممارسة",
            },
        }

    async def classify_intent(self, query: str) -> tuple[str, str, float]:
        """
        Returns: (domain, sub_intent, confidence)
        """
        query_lower = query.lower()

        # Level 1: Domain classification
        domain_scores = {}
        for domain, patterns in self.domain_patterns.items():
            score = sum(1 for p in patterns if re.search(p, query_lower))
            domain_scores[domain] = score

        # Default to advisory if no match
        if max(domain_scores.values(), default=0) == 0:
            return "advisory", "general_advice", 0.5

        best_domain = max(domain_scores, key=domain_scores.get)
        domain_confidence = min(0.95, 0.5 + domain_scores[best_domain] * 0.15)

        # Level 2: Sub-intent classification
        sub_scores = {}
        if best_domain in self.sub_intent_patterns:
            for sub_intent, pattern in self.sub_intent_patterns[best_domain].items():
                if re.search(pattern, query_lower):
                    sub_scores[sub_intent] = 1.0

        if sub_scores:
            best_sub = max(sub_scores, key=sub_scores.get)
            sub_confidence = 0.9
        else:
            # Default sub-intent for domain
            defaults = {
                "remote_sensing": "full_analysis",
                "crop_model": "simulate_current",
                "market": "price_current",
                "advisory": "general_advice",
            }
            best_sub = defaults.get(best_domain, "general_advice")
            sub_confidence = 0.6

        overall_confidence = (domain_confidence + sub_confidence) / 2

        return best_domain, best_sub, round(overall_confidence, 2)
