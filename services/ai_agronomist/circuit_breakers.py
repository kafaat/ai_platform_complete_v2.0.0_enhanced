class CircuitBreaker:
    def __init__(self, threshold=3):
        self.failures = 0
        self.threshold = threshold

    def record_failure(self):
        self.failures += 1

    @property
    def open(self):
        return self.failures >= self.threshold
