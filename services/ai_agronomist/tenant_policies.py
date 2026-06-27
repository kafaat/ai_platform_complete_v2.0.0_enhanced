class TenantPolicyStore:
    def __init__(self):
        self._p = {}

    def set_policy(self, tenant_id, policy):
        self._p[tenant_id] = policy

    def get_policy(self, tenant_id):
        return self._p.get(tenant_id, {})
