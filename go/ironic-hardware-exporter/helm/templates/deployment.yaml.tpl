apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "ironic-hardware-exporter.fullname" . }}
  labels:
    {{- include "ironic-hardware-exporter.labels" . | nindent 4 }}
spec:
  replicas: 1
  selector:
    matchLabels:
      {{- include "ironic-hardware-exporter.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      {{- with .Values.podAnnotations }}
      annotations:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      labels:
        {{- include "ironic-hardware-exporter.labels" . | nindent 8 }}
        {{- with .Values.podLabels }}
        {{- toYaml . | nindent 8 }}
        {{- end }}
    spec:
      {{- with .Values.imagePullSecrets }}
      imagePullSecrets:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      automountServiceAccountToken: false
      {{- with .Values.podSecurityContext }}
      securityContext:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      containers:
        - name: {{ .Chart.Name }}
          {{- with .Values.securityContext }}
          securityContext:
            {{- toYaml . | nindent 12 }}
          {{- end }}
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag | default .Chart.AppVersion }}"
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          ports:
            - name: http
              containerPort: {{ .Values.service.port }}
              protocol: TCP
          env:
            - name: RABBITMQ_HOST
              value: {{ .Values.rabbitmq.host | quote }}
            {{- if .Values.rabbitmq.port }}
            - name: RABBITMQ_PORT
              value: {{ .Values.rabbitmq.port | quote }}
            {{- end }}
            - name: RABBITMQ_VHOST
              value: {{ .Values.rabbitmq.vhost | quote }}
            - name: RABBITMQ_USERNAME
              value: {{ .Values.rabbitmq.username | quote }}
            - name: RABBITMQ_EXCHANGE
              value: {{ .Values.rabbitmq.exchange | quote }}
            - name: RABBITMQ_QUEUE
              value: {{ .Values.rabbitmq.queue | quote }}
            - name: RABBITMQ_ROUTING_KEY
              value: {{ .Values.rabbitmq.routingKey | quote }}
            - name: RABBITMQ_STATES_QUEUE
              value: {{ .Values.rabbitmq.statesQueue | quote }}
            - name: RABBITMQ_STATES_ROUTING_KEY
              value: {{ .Values.rabbitmq.statesRoutingKey | quote }}
            - name: RABBITMQ_TLS_ENABLED
              value: {{ .Values.rabbitmq.tls.enabled | quote }}
            {{- if .Values.rabbitmq.tls.serverName }}
            - name: RABBITMQ_TLS_SERVER_NAME
              value: {{ .Values.rabbitmq.tls.serverName | quote }}
            {{- end }}
            {{- if and .Values.rabbitmq.tls.enabled .Values.rabbitmq.tls.caSecretName }}
            - name: RABBITMQ_CA_CERT_PATH
              value: /etc/rabbitmq/tls/ca.crt
            {{- end }}
            - name: SERVER_PORT
              value: {{ .Values.service.port | quote }}
            - name: RABBITMQ_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: {{ required "rabbitmq.existingSecret is required" .Values.rabbitmq.existingSecret }}
                  key: {{ .Values.rabbitmq.passwordSecretKey | default "password" }}
          {{- with .Values.livenessProbe }}
          livenessProbe:
            {{- toYaml . | nindent 12 }}
          {{- end }}
          {{- with .Values.readinessProbe }}
          readinessProbe:
            {{- toYaml . | nindent 12 }}
          {{- end }}
          {{- with .Values.resources }}
          resources:
            {{- toYaml . | nindent 12 }}
          {{- end }}
          volumeMounts:
            {{- if and .Values.rabbitmq.tls.enabled .Values.rabbitmq.tls.caSecretName }}
            - name: rabbitmq-ca
              mountPath: /etc/rabbitmq/tls
              readOnly: true
            {{- end }}
            {{- with .Values.volumeMounts }}
            {{- toYaml . | nindent 12 }}
            {{- end }}
      volumes:
        {{- if and .Values.rabbitmq.tls.enabled .Values.rabbitmq.tls.caSecretName }}
        - name: rabbitmq-ca
          secret:
            secretName: {{ .Values.rabbitmq.tls.caSecretName }}
            items:
              - key: {{ .Values.rabbitmq.tls.caSecretKey | default "ca.crt" }}
                path: ca.crt
        {{- end }}
        {{- with .Values.volumes }}
        {{- toYaml . | nindent 8 }}
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
