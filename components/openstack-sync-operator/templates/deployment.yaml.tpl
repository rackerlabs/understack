{{- $enabledHooks := dict -}}
{{- $hookEnv := dict -}}
{{- $_ := dict -}}
{{- $configuredHooks := include "openstack-sync-operator.configuredHooks" . | fromYaml -}}
{{- range $hookName, $hook := default dict $configuredHooks -}}
{{- $hookEnabled := eq $hook.enabled true -}}
{{- if $hookEnabled -}}
{{- $_ = set $enabledHooks $hookName $hook -}}
{{- end -}}
{{- $envPrefix := get $hook "envPrefix" -}}
{{- if $envPrefix -}}
{{- $_ = set $hookEnv (printf "%s_ENABLED" $envPrefix) (ternary "true" "false" $hookEnabled) -}}
{{- $crdPath := get $hook "crd" -}}
{{- if $crdPath -}}
{{- $crd := include "openstack-sync-operator.hookCrd" (list $ $hookName $hook) | fromYaml -}}
{{- $_ = set $hookEnv (printf "%s_CRD_API_VERSION" $envPrefix) $crd.apiVersion -}}
{{- $_ = set $hookEnv (printf "%s_CRD_KIND" $envPrefix) $crd.kind -}}
{{- $_ = set $hookEnv (printf "%s_CRD_RESOURCE" $envPrefix) $crd.resource -}}
{{- $_ = set $hookEnv (printf "%s_STATUS_ENABLED" $envPrefix) (ternary "true" "false" $crd.hasStatus) -}}
{{- end -}}
{{- range $envName, $envValue := default dict $hook.env }}
{{- $name := printf "%s_%s" $envPrefix $envName -}}
{{- if hasKey $hookEnv $name }}
{{- fail (printf "duplicate hook environment variable %s" $name) }}
{{- end }}
{{- $_ = set $hookEnv $name (toString $envValue) -}}
{{- end }}
{{- end }}
{{- end -}}
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "openstack-sync-operator.fullname" . }}
  labels:
    {{- include "openstack-sync-operator.labels" . | nindent 4 }}
    app.kubernetes.io/component: controller
spec:
  replicas: {{ .Values.replicaCount }}
  selector:
    matchLabels:
      {{- include "openstack-sync-operator.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      labels:
        {{- include "openstack-sync-operator.selectorLabels" . | nindent 8 }}
        app.kubernetes.io/component: controller
        {{- with .Values.podLabels }}
        {{- toYaml . | nindent 8 }}
        {{- end }}
      annotations:
        checksum/openstack-sync-operator-hooks: {{ include "openstack-sync-operator.hookConfigChecksum" . | quote }}
        {{- with .Values.podAnnotations }}
        {{- toYaml . | nindent 8 }}
        {{- end }}
    spec:
      serviceAccountName: {{ include "openstack-sync-operator.serviceAccountName" . }}
      {{- if gt (len $enabledHooks) 0 }}
      initContainers:
      - name: verify-hooks
        image: "{{ .Values.image.repository }}:{{ .Values.image.tag | default .Chart.AppVersion }}"
        imagePullPolicy: {{ .Values.image.pullPolicy }}
        command:
        - /bin/sh
        - -ec
        - |
          missing=0
          {{- range $hookName, $hook := $enabledHooks }}
          {{- $hookPath := required (printf "hooks.%s.path is required when hook is enabled" $hookName) $hook.path }}
          if [ ! -x {{ $hookPath | quote }} ]; then
            echo {{ printf "enabled hook %s missing or not executable: %s" $hookName $hookPath | quote }} >&2
            missing=1
          fi
          {{- end }}
          exit "${missing}"
      {{- end }}
      containers:
      - name: shell-operator
        image: "{{ .Values.image.repository }}:{{ .Values.image.tag | default .Chart.AppVersion }}"
        imagePullPolicy: {{ .Values.image.pullPolicy }}
        ports:
        - name: http
          containerPort: 9115
          protocol: TCP
        livenessProbe:
          tcpSocket:
            port: http
          initialDelaySeconds: 10
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 6
        readinessProbe:
          tcpSocket:
            port: http
          initialDelaySeconds: 5
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3
        env:
        - name: POD_NAMESPACE
          valueFrom:
            fieldRef:
              fieldPath: metadata.namespace
        {{- range $envName := keys $hookEnv | sortAlpha }}
        - name: {{ $envName }}
          value: {{ get $hookEnv $envName | quote }}
        {{- end }}
        {{- with .Values.resources }}
        resources:
          {{- toYaml . | nindent 12 }}
        {{- end }}
      {{- with .Values.nodeSelector }}
      nodeSelector:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with .Values.affinity }}
      affinity:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with .Values.tolerations }}
      tolerations:
        {{- toYaml . | nindent 8 }}
      {{- end }}
