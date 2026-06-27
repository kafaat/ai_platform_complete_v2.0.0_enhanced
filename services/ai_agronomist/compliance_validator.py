class ComplianceValidator:
    def validate(self, recommendation):
        violations = []
        if recommendation.get("type") == "pesticide" and not recommendation.get("phi_days"):
            violations.append("Missing PHI")
        return {"valid": not violations, "violations": violations}
