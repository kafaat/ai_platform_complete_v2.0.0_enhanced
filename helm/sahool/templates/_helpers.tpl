{{- define "sahool.name" -}}sahool{{- end -}}
{{- define "sahool.labels" -}}
app.kubernetes.io/name: sahool
app.kubernetes.io/part-of: sahool-platform
app.kubernetes.io/managed-by: Helm
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end -}}

{{- /*
upstreams.conf for the gateway: one upstream per workload (name with "-" -> "_", the
names files/gateway/routes.conf uses; a disabled workload gets a `down` server) plus the auth service that answers
`GET /v1/auth/verify`. Service names resolve once at start-up (stable ClusterIPs); an
absent Service stops nginx from starting, so the gateway never runs without its verifier.
*/}}
{{- define "sahool.gatewayUpstreams" -}}
# Auth is resolved per request, not at start-up: nginx starts even while the auth Service
# does not exist yet (the sahool-auth workload is still rolling out, or is disabled); every
# auth_request then fails with 500 and /auth/ with 502, so nothing passes unverified.
resolver {{ required "gateway.resolver is required: the cluster DNS Service that resolves the auth host per request" .Values.gateway.resolver }} valid=10s ipv6=off;
resolver_timeout 3s;
map $host $sahool_auth_addr { default "{{ required "gateway.auth.serviceName is required: the gateway verifies every protected request with auth GET /v1/auth/verify" .Values.gateway.auth.serviceName }}.{{ .Values.namespace.name }}.svc.{{ .Values.gateway.clusterDomain | default "cluster.local" }}:{{ .Values.gateway.auth.port }}"; }
{{- range $name, $svc := .Values.workloads }}
{{- if not $svc.pathPrefix }}
{{- /* W3-09: no public route (auth is reached through $sahool_auth_addr; internal-only
workloads not at all). An upstream nginx resolves at start-up would tie the gateway's boot
to a Service it never proxies to. */}}
{{- else if $svc.enabled }}
upstream {{ $name | replace "-" "_" }} { server {{ $name }}:{{ $svc.port }}; keepalive 8; }
{{- else }}
# {{ $name }} is disabled: its route answers 502 instead of resolving a missing Service.
upstream {{ $name | replace "-" "_" }} { server 127.0.0.1:9 down; }
{{- end }}
{{- end }}
{{- end -}}
