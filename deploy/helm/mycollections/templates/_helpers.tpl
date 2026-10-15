{{- define "mycollections.labels" -}}
app.kubernetes.io/part-of: mycollections
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
{{- with .Values.commonLabels }}
{{ toYaml . }}
{{- end }}
{{- end }}

{{/* Sélecteurs FIGÉS — ceux du déploiement d'origine (kustomize, commonLabels). */}}
{{- define "mycollections.selecteur" -}}
app: {{ .app }}
app.kubernetes.io/part-of: mycollections
{{- end }}

{{- define "mycollections.image" -}}
{{- if not .image.tag }}{{ fail (printf "images.%s.tag est obligatoire (étiquette fixe)" .nom) }}{{ end -}}
{{ .image.repository }}:{{ .image.tag }}
{{- end }}

{{- define "mycollections.envFrom" -}}
- configMapRef:
    name: myrag-config
{{- with .Values.backend.existingSecret }}
- secretRef:
    name: {{ . }}
{{- end }}
{{- end }}

{{- define "mycollections.securiteConteneur" -}}
readOnlyRootFilesystem: true
allowPrivilegeEscalation: false
capabilities:
  drop: ["ALL"]
{{- end }}
