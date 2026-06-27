class ChaosRuntime:
    def inject_failure(self, service):
        return {"service": service, "status": "simulated_failure"}
