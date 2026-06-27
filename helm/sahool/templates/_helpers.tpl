{{- define "sahool.name" -}}sahool{{- end -}}
{{- define "sahool.labels" -}}
app.kubernetes.io/name: sahool
app.kubernetes.io/part-of: sahool-platform
app.kubernetes.io/managed-by: Helm
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end -}}
