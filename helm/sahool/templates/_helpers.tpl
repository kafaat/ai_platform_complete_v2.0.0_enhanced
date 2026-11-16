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
upstream sahool_auth { server {{ required "gateway.auth.serviceName is required: the gateway verifies every protected request with auth GET /v1/auth/verify" .Values.gateway.auth.serviceName }}:{{ .Values.gateway.auth.port }}; keepalive 8; }
{{- range $name, $svc := .Values.workloads }}
{{- if $svc.enabled }}
upstream {{ $name | replace "-" "_" }} { server {{ $name }}:{{ $svc.port }}; keepalive 8; }
{{- else }}
# {{ $name }} is disabled: its route answers 502 instead of resolving a missing Service.
upstream {{ $name | replace "-" "_" }} { server 127.0.0.1:9 down; }
{{- end }}
{{- end }}
{{- end -}}
