apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "dexop.fullname" . }}-controller-manager
  labels:
    control-plane: controller-manager
    {{- include "dexop.labels" . | nindent 4 }}
spec:
  replicas: {{ .Values.replicaCount }}
  selector:
    matchLabels:
      {{- include "dexop.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      {{- with .Values.podAnnotations }}
      annotations:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      labels:
        {{- include "dexop.labels" . | nindent 8 }}
        {{- with .Values.podLabels }}
        {{- toYaml . | nindent 8 }}
        {{- end }}
    spec:
      {{- with .Values.imagePullSecrets }}
      imagePullSecrets:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      serviceAccountName: {{ include "dexop.serviceAccountName" . }}
      securityContext:
        {{- toYaml .Values.podSecurityContext | nindent 8 }}
      terminationGracePeriodSeconds: 10
      containers:
        - name: manager
          args:
          - --metrics-bind-address=:8443
          - --leader-elect
          - --health-probe-bind-address=:8081
          - --dex-ca-path=/run/secrets/dex/ca.pem
          - --dex-cert-path=/run/secrets/dex/tls.crt
          - --dex-key-path=/run/secrets/dex/tls.key
          - --dex-host={{ .Values.dex.address }}
          {{ with .Values.dex.issuer }}
          - --dex-issuer={{ . }}
          {{- end }}
          command:
          - /manager
          securityContext:
            {{- toYaml .Values.securityContext | nindent 12 }}
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag | default .Chart.AppVersion }}"
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          livenessProbe:
            {{- toYaml .Values.livenessProbe | nindent 12 }}
          readinessProbe:
            {{- toYaml .Values.readinessProbe | nindent 12 }}
          resources:
            {{- toYaml .Values.resources | nindent 12 }}
          volumeMounts:
          - mountPath: /run/secrets/dex/
            name: client-secret
            readOnly: true
          {{- with .Values.volumeMounts }}
            {{- toYaml . | nindent 12 }}
          {{- end }}
      volumes:
        {{- with .Values.volumes }}
          {{- toYaml . | nindent 12 }}
        {{- end }}
        - name: client-secret
          secret:
            secretName: {{ .Values.dex.secret }}
            optional: false
