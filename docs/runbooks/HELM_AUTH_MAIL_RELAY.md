# Helm auth: operator-managed in-cluster SMTP relay (default OFF)

Decision: [HELM-AUTH-NO-SMTP-SMS-EGRESS-01](https://github.com/kafaat/ai_platform_complete_v2.0.0_enhanced/pull/1510#issuecomment-6977890467).

**Scope:** Chart-only opt-in for the existing `sahool-auth` SMTP client. The chart
does **not** deploy a relay, choose a third-party relay image, provision a mail
provider account, create SMTP secrets, enable SMS, or modify Railway. Source
change and CI success are **not** authorization to deploy to production.

## Contract

- `authEmailRelay.enabled=false` by default in both overlays. No `SMTP_*`
  environment variables and no additional mail policies are rendered.
- An operator must provision a same-namespace Kubernetes **Service backed by
  Pods** with the exact `app.kubernetes.io/component` label configured in
  `authEmailRelay.podComponent`. Do not use `ExternalName`, bare Internet IPs,
  a public SMTP host or a Service with unrelated endpoints. Review and pin the
  relay image, license and configuration through the operator's process.
- The relay certificate must be trusted by the auth image and have a SAN for
  `<serviceName>.<namespace>.svc.<gateway.clusterDomain>`. The existing
  `services/auth/main.py` uses SMTP AUTH with STARTTLS, without an
  insecure-certificate bypass. The relay must refuse SMTP without TLS and
  authentication. Its upstream mail provider egress, TLS identity, rate limits,
  queue persistence, retry policy, and spam/open-relay protections are an
  **operator responsibility**; this chart does not grant relay public egress.
- Store the SMTP username/password in an existing Kubernetes Secret with
  `username` / `password` keys (configurable). Only `secretKeyRef` is
  emitted. No password or OTP may appear in Helm values, rendered manifests,
  CI artifacts or application logs.
- `SMTP_HOST` is synthesized from the internal Kubernetes Service DNS name;
  `SMTP_PORT` is restricted to 587 and `SMTP_FROM` must be explicitly set.
  `SMS_PROVIDER_URL` and `SMS_API_KEY` remain absent; SMS requires its own
  separately approved provider-specific egress policy.
- When enabled, the chart's broad `sahool-default-deny` egress rule
  **excludes `sahool-auth`**. A dedicated auth egress policy permits only:
  the labeled relay Pods on TCP 587, a specific labeled DNS Pod on TCP/UDP 53,
  and two **operator-specified** labeled peers (`database` and `redis`)
  on explicit non-SMTP TCP ports. No arbitrary IP or Internet destination is
  accepted by this chart integration. Database/Redis outside Kubernetes need a
  separately reviewed network design; do not work around this with
  `0.0.0.0/0` or a general namespace selector.
- The chart also emits a relay ingress policy admitting labeled auth Pods on
  TCP 587. Kubernetes NetworkPolicies are **additive**: other namespace or
  cluster policies can still permit traffic. Their effective union and the
  CNI's enforcement must be tested on **staging**. Pod labels and Service
  Endpoints must be measured from live Kubernetes, not trusted from Helm YAML.

## Before any staging enablement

1. Establish a separate operator-managed relay Service, TLS certificate,
   credentials Secret, and outbound mail provider policy. Verify endpoint
   labels, Service selectors, and TLS SAN. Disable unencrypted SMTP and
   unauthenticated mail relay. Confirm the image provenance and license.
2. Identify the actual database and Redis Pods and their namespaces and
   listening TCP ports. Populate both entries under
   `authEmailRelay.dependencyEgress`. Check the DNS Pod label in your
   cluster (the default is `kube-system` / `k8s-app=kube-dns`).
3. Create an explicit private Helm values overlay based on the **test-only
   shape** in `tests_v9/fixtures/helm_auth_mail_relay.yaml`; never copy
   test-only names or store credentials in it.
4. Execute `helm lint` and `helm template` against staging and production
   overlays plus the opt-in values. The `helm-readiness` CI job uses the pinned
   Helm v3.16.4 binary with verified SHA-256 and tests the disabled and opt-in
   configurations. A missing Helm binary fails under
   `HELM_RENDER_REQUIRED=1`.
5. Inspect the rendered Deployment and NetworkPolicy selectors. There must be
   no direct public SMTP (25/465/587), no general auth HTTPS, and no
   `SMS_PROVIDER_URL` in auth's container. Inspect any other NetworkPolicies
   selecting auth or the relay; their unions may widen egress/ingress.
6. With an isolated staging test account and a test mail sink, verify reset
   and OTP email success, TLS verification, AUTH failures, relay-down behavior,
   client and server port restrictions, and no OTP/token leakage. Use a
   negative network probe: auth-to-public-SMTP blocked; auth-to-relay allowed;
   unapproved Pod-to-relay denied; DB/Redis and DNS remain functional.
7. Record operator receipts for the CNI/network probes, DNS identity,
   TLS/cert validation, and user-flow tests. Only after that may the owner
   separately authorize a production change.

## Status

`DESIGN_APPROVED / HELM_OPT_IN_CODE / STAGING_RUNTIME_NOT_VERIFIED /
PRODUCTION_NOT_AUTHORIZED`.

This implementation cannot independently certify SMTP delivery, mail-provider
egress, CNI policy enforcement, live credentials or commercial relay licensing.
