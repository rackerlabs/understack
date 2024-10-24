# schema

## argo-workflows

```bash
curl -o argo-workflows.json https://raw.githubusercontent.com/argoproj/argo-workflows/master/api/jsonschema/schema.json
```

## flavor.schema

Used to define hardware identification / mapping for Ironic hardware to Nova flavors.
The flavors hook uses these files to set properties automatically on the nodes.
