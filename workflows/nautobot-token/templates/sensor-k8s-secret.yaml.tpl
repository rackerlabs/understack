apiVersion: argoproj.io/v1alpha1
kind: Sensor
metadata:
  name: nautobot-token
  namespace: "{{ .Release.Namespace }}"
  annotations:
    workflows.argoproj.io/title: Nautobot Token
    workflows.argoproj.io/description: |+
      Triggered when the Kubernetes Nautobot token secret is created,
      this process ensures the user is created in Nautobot and a corresponding token is provisioned.
spec:
  eventBusName: nautobot-token
  template:
    serviceAccountName: k8s-job-create
  dependencies:
    - name: nautobot-token-upsert
      eventSourceName: nautobot-token
      eventName: nautobot-token-upsert
  triggers:
    - template:
        name: nautobot-users
        k8s:
          operation: create
          parameters:
            # Pass the body.data as JSON string into the Job environment
            - src:
                dependencyName: nautobot-token-upsert
                dataKey: body.data
                transformer:
                  jqFilter: '@json'
              dest: spec.template.spec.containers.0.env.0.value
          source:
            resource:
              apiVersion: batch/v1
              kind: Job
              metadata:
                generateName: nautobot-create-token-
                namespace: nautobot
              spec:
                template:
                  spec:
                    containers:
                      - name: nautobot-create-token
                        image: ghcr.io/rackerlabs/understack/ansible:latest
                        imagePullPolicy: Always
                        command:
                          - "ansible-runner"
                          - "run"
                          - "/runner"
                          - "--playbook"
                          - "nautobot-user-token.yaml"
                        env:
                          - name: EXTRA_VARS
                            value: ""  # Will be populated by the Sensor mapping
                          - name: NAUTOBOT_TOKEN
                            valueFrom:
                              secretKeyRef:
                                name: nautobot-superuser
                                key: apitoken
                        volumeMounts:
                          - name: ansible-inventory
                            mountPath: /runner/inventory/
                          - name: ansible-group-vars
                            mountPath: /runner/inventory/group_vars/
                    volumes:
                      - name: runner-data
                        emptyDir: {}
                      - name: ansible-inventory
                        configMap:
                          name: ansible-inventory
                      - name: ansible-group-vars
                        configMap:
                          name: ansible-group-vars
                    restartPolicy: OnFailure
