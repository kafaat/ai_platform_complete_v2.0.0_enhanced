#!/usr/bin/env python3
import logging as _log

_audit = _log.getLogger("guardrails.chemical_tier")
#!/usr/bin/env python3
"""
Tier 1: Chemical Safety Guardrails
Validates pesticides, fertilizers, and chemical inputs against:
- International banned substances (Stockholm Convention, etc.)
- Maximum safe dosages by crop
- Application timing restrictions
- Buffer zones and re-entry intervals
"""


class ChemicalSafetyTier:
    """
    Chemical safety validation for agricultural inputs.
    """

    # Internationally banned substances (Stockholm Convention + EU + EPA)
    BANNED_CHEMICALS = {
        "methyl_bromide": {"reason": "محظور بموجب بروتوكول مونتريال", "severity": "CRITICAL"},
        "ddt": {"reason": "محظور بموجب اتفاقية استكهولم", "severity": "CRITICAL"},
        "aldrin": {"reason": "مبيد عضوي كلوري محظور", "severity": "CRITICAL"},
        "chlordane": {"reason": "مبيد عضوي كلوري محظور", "severity": "CRITICAL"},
        "dieldrin": {"reason": "مبيد عضوي كلوري محظور", "severity": "CRITICAL"},
        "endrin": {"reason": "مبيد عضوي كلوري محظور", "severity": "CRITICAL"},
        "heptachlor": {"reason": "مبيد عضوي كلوري محظور", "severity": "CRITICAL"},
        "hexachlorobenzene": {"reason": "مبيد عضوي كلوري محظور", "severity": "CRITICAL"},
        "mirex": {"reason": "مبيد عضوي كلوري محظور", "severity": "CRITICAL"},
        "toxaphene": {"reason": "مبيد عضوي كلوري محظور", "severity": "CRITICAL"},
        "lindane": {"reason": "محظور في الاتحاد الأوروبي", "severity": "CRITICAL"},
        "paraquat": {"reason": "محظور في 53 دولة — سمية عالية", "severity": "CRITICAL"},
        "endosulfan": {"reason": "محظور بموجب اتفاقية استكهولم", "severity": "CRITICAL"},
        "atrazine": {"reason": "مقيد — تلوث مياه جوفية", "severity": "HIGH"},
        "glyphosate": {"reason": "مقيد — IARC Group 2A محتمل مسرطن", "severity": "MEDIUM"},
    }

    # Maximum safe dosages by crop (kg active ingredient / ha)
    MAX_DOSAGES = {
        "glyphosate": {
            "max_kg_ha": 2.0,
            "crops": {"wheat": 1.5, "barley": 1.5, "maize": 2.0, "sorghum": 1.8, "millet": 1.5},
            "buffer_zone_m": 5,
            "reentry_hours": 4,
        },
        "chlorpyrifos": {
            "max_kg_ha": 0.5,
            "crops": {"wheat": 0.4, "maize": 0.5, "cotton": 0.6},
            "buffer_zone_m": 10,
            "reentry_hours": 24,
            "banned_crops": ["tomato", "potato", "apple"],  # Highly toxic to these
        },
        "imidacloprid": {
            "max_kg_ha": 0.5,
            "crops": {"wheat": 0.3, "cotton": 0.5, "rice": 0.4},
            "buffer_zone_m": 5,
            "reentry_hours": 12,
        },
        "mancozeb": {
            "max_kg_ha": 3.0,
            "crops": {"potato": 2.5, "tomato": 2.0, "grape": 2.5},
            "buffer_zone_m": 3,
            "reentry_hours": 6,
        },
        "propiconazole": {
            "max_kg_ha": 0.5,
            "crops": {"wheat": 0.5, "barley": 0.4},
            "buffer_zone_m": 5,
            "reentry_hours": 12,
        },
        "abamectin": {
            "max_kg_ha": 0.03,
            "crops": {"tomato": 0.02, "cotton": 0.03},
            "buffer_zone_m": 10,
            "reentry_hours": 48,
        },
        "sulfur": {
            "max_kg_ha": 5.0,
            "crops": {"grape": 4.0, "apple": 3.0, "tomato": 3.0},
            "buffer_zone_m": 0,
            "reentry_hours": 0,
        },
    }

    # Fertilizer safety limits
    FERTILIZER_LIMITS = {
        "N": {"max_kg_ha_year": 200, "max_single_application": 80, "water_risk_threshold": 150},
        "P": {"max_kg_ha_year": 100, "max_single_application": 50},
        "K": {"max_kg_ha_year": 150, "max_single_application": 60},
    }

    async def validate(self, action_type: str, action_data: dict, farm_context: dict) -> dict:
        findings = []
        suggestions = []
        passed = True

        if action_type == "pesticide":
            chemical = action_data.get("chemical", "").lower().strip()
            dosage_kg_ha = action_data.get("dosage_kg_ha", 0)
            crop = action_data.get("crop", "")

            # Check banned substances
            if chemical in self.BANNED_CHEMICALS:
                banned = self.BANNED_CHEMICALS[chemical]
                findings.append(
                    {
                        "severity": banned["severity"],
                        "message": f"Chemical {chemical} is banned: {banned['reason']}",
                        "message_ar": f"المادة {chemical} **محظورة دولياً**: {banned['reason']}",
                        "rule": "banned_substance",
                    }
                )
                passed = False

            # Check max dosages
            if chemical in self.MAX_DOSAGES:
                limits = self.MAX_DOSAGES[chemical]
                crop_limit = limits["crops"].get(crop, limits["max_kg_ha"])

                if dosage_kg_ha > limits["max_kg_ha"]:
                    findings.append(
                        {
                            "severity": "HIGH",
                            "message": f"Dosage {dosage_kg_ha} kg/ha exceeds absolute max {limits['max_kg_ha']} for {chemical}",
                            "message_ar": f"الجرعة {dosage_kg_ha} كجم/هكتار تتجاوز الحد الأقصى المسموح ({limits['max_kg_ha']}) لمادة {chemical}",
                            "rule": "max_dosage_exceeded",
                        }
                    )
                    passed = False
                    suggestions.append(
                        {
                            "field": "dosage_kg_ha",
                            "value": crop_limit,
                            "text": f"Reduce dosage to {crop_limit} kg/ha for {crop}",
                            "text_ar": f"قلل الجرعة إلى {crop_limit} كجم/هكتار لمحصول {crop}",
                        }
                    )
                elif dosage_kg_ha > crop_limit:
                    findings.append(
                        {
                            "severity": "MEDIUM",
                            "message": f"Dosage exceeds crop-specific limit {crop_limit} for {crop}",
                            "message_ar": f"الجرعة تتجاوز الحد المخصص لمحصول {crop} ({crop_limit} كجم/هكتار)",
                            "rule": "crop_dosage_exceeded",
                        }
                    )
                    suggestions.append(
                        {
                            "field": "dosage_kg_ha",
                            "value": crop_limit,
                            "text": f"Use {crop_limit} kg/ha for {crop}",
                            "text_ar": f"استخدم {crop_limit} كجم/هكتار لمحصول {crop}",
                        }
                    )

                # Check banned crops
                if crop in limits.get("banned_crops", []):
                    findings.append(
                        {
                            "severity": "CRITICAL",
                            "message": f"{chemical} is banned for {crop} due to high toxicity",
                            "message_ar": f"مادة {chemical} **محظورة** على محصول {crop} بسبب السمية العالية",
                            "rule": "banned_for_crop",
                        }
                    )
                    passed = False
            else:
                # Unknown chemical — require human approval
                findings.append(
                    {
                        "severity": "HIGH",
                        "message": f"Chemical {chemical} not in approved database — requires expert review",
                        "message_ar": f"مادة {chemical} غير موجودة في قاعدة البيانات المعتمدة — يتطلب مراجعة خبير",
                        "rule": "unknown_chemical",
                    }
                )
                passed = False

        elif action_type == "fertilization":
            n_kg = action_data.get("N_kg_ha", 0)
            p_kg = action_data.get("P_kg_ha", 0)
            k_kg = action_data.get("K_kg_ha", 0)

            # Check N limits
            if n_kg > self.FERTILIZER_LIMITS["N"]["max_single_application"]:
                findings.append(
                    {
                        "severity": "HIGH",
                        "message": f"Nitrogen application {n_kg} kg/ha exceeds safe single-application limit",
                        "message_ar": f"تطبيق النيتروجين {n_kg} كجم/هكتار يتجاوز الحد الآمن للتطبيق الواحد ({self.FERTILIZER_LIMITS['N']['max_single_application']})",
                        "rule": "n_max_single_exceeded",
                    }
                )
                passed = False
                suggestions.append(
                    {
                        "field": "N_kg_ha",
                        "value": self.FERTILIZER_LIMITS["N"]["max_single_application"],
                        "text": "Split into multiple applications",
                        "text_ar": "قسّم التسميد على دفعات متعددة",
                    }
                )

            # Check water pollution risk
            annual_n = farm_context.get("annual_N_kg_ha", 0) + n_kg
            if annual_n > self.FERTILIZER_LIMITS["N"]["water_risk_threshold"]:
                findings.append(
                    {
                        "severity": "MEDIUM",
                        "message": f"Annual N total {annual_n} kg/ha approaches water pollution threshold",
                        "message_ar": f"إجمالي النيتروجين السنوي {annual_n} كجم/هكتار يقترب من حد تلوث المياه الجوفية",
                        "rule": "n_water_pollution_risk",
                    }
                )

            # Check P single-application limit
            if p_kg > self.FERTILIZER_LIMITS["P"]["max_single_application"]:
                findings.append(
                    {
                        "severity": "HIGH",
                        "message": f"Phosphorus application {p_kg} kg/ha exceeds safe single-application limit",
                        "message_ar": f"تطبيق الفوسفور {p_kg} كجم/هكتار يتجاوز الحد الآمن للتطبيق الواحد ({self.FERTILIZER_LIMITS['P']['max_single_application']})",
                        "rule": "p_max_single_exceeded",
                    }
                )
                passed = False
                suggestions.append(
                    {
                        "field": "P_kg_ha",
                        "value": self.FERTILIZER_LIMITS["P"]["max_single_application"],
                        "text": "Reduce phosphorus to the safe single-application limit",
                        "text_ar": "قلّل الفوسفور إلى الحد الآمن للتطبيق الواحد",
                    }
                )

            # Check K single-application limit
            if k_kg > self.FERTILIZER_LIMITS["K"]["max_single_application"]:
                findings.append(
                    {
                        "severity": "HIGH",
                        "message": f"Potassium application {k_kg} kg/ha exceeds safe single-application limit",
                        "message_ar": f"تطبيق البوتاسيوم {k_kg} كجم/هكتار يتجاوز الحد الآمن للتطبيق الواحد ({self.FERTILIZER_LIMITS['K']['max_single_application']})",
                        "rule": "k_max_single_exceeded",
                    }
                )
                passed = False
                suggestions.append(
                    {
                        "field": "K_kg_ha",
                        "value": self.FERTILIZER_LIMITS["K"]["max_single_application"],
                        "text": "Reduce potassium to the safe single-application limit",
                        "text_ar": "قلّل البوتاسيوم إلى الحد الآمن للتطبيق الواحد",
                    }
                )

        return {
            "tier": "chemical",
            "passed": passed,
            "findings": findings,
            "suggestions": suggestions,
        }
