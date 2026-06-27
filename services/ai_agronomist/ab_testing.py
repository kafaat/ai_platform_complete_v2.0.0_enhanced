class ABTestingRuntime:
    def compare(self, a, b):
        return {"winner": "A" if a.get("confidence", 0) >= b.get("confidence", 0) else "B"}
