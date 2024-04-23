# argo_python

A quick helper method to write kubernetes secrets. This accomplishes a couple things.

1) Allows us to share sensitive data to subsequent Workflows.
2) Sets metadata.ownerReferences (to the Pod), which allows this secret to be garbage collected upon Pod removal.

note: to add the ownerReference for garbage collection, the Pod's uid needs to be obtained. This can either be done by
providing get permission on the pods resource for the service account running this Pod, or by passing the Pod uid into
the container with something like:

```yaml
        env:
        - name: KUBERNETES_POD_UID
          valueFrom:
            fieldRef:
              fieldPath: metadata.uid
```

### Example
```python

    from argo_python import ArgoWorkflow
    import base64

    data = {
        'username': base64.b64encode("<username>".encode("utf-8")).decode(),
        'password': base64.b64encode("<password>".encode("utf-8")).decode(),
    }

    workflow = ArgoWorkflow()
    secret_name = workflow.create_secret("creds", data)
    print(secret_name)

    # example output: "creds-97794d2b-338c-44c6-8587-e3086e6a1bf7"
```

