{{- if .Values.prometheus.enabled }}
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: {{ include "nautobotop.fullname" . }}
  labels:
    {{- include "nautobotop.labels" . | nindent 4 }}
    {{- with .Values.prometheus.additionalLabels }}
    {{- toYaml . | nindent 4 }}
    {{- end }}
spec:
  groups:
    - name: nautobotop.sync
      rules:
        - alert: NautobotopSyncItemFailures
          # Fires when one or more individual Nautobot items have been
          # consistently failing to sync for longer than one sync interval.
          # This means a human must fix the data (e.g. a VLAN group whose range
          # cannot be shrunk while VLANs exist in it). The item and the reason
          # are visible in Status.NautobotStatusReport on the Nautobot CR:
          #
          #   kubectl get nautobot <name> -o yaml
          expr: nautobotop_sync_item_failures > 0
          for: {{ .Values.prometheus.alertForDuration }}
          labels:
            severity: warning
          annotations:
            summary: >-
              Nautobot sync item failures on {{ "{{ $labels.nautobot }}" }}
              (resource: {{ "{{ $labels.resource }}" }})
            description: >-
              {{ "{{ $value | humanize }}" }} item(s) in the
              {{ "{{ $labels.resource }}" }} sync have been failing for more
              than {{ .Values.prometheus.alertForDuration }} on Nautobot CR
              {{ "{{ $labels.nautobot }}" }}. The items are rejected by Nautobot
              (usually a data problem) and will keep failing until the input is
              fixed. Check Status.NautobotStatusReport for details:
                kubectl get nautobot {{ "{{ $labels.nautobot }}" }} -o yaml
{{- end }}
