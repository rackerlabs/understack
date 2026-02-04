# Overriding OpenStack Services Config

If you need to override any settings for any of the OpenStack services or add in
additional configuration snippets, you can do so by defining additional mounts
in your deploy repo.

For example if you wanted to add the following into neutron-server:

```ini
[mysection]
somevalue = 1
```

Firstly you would create either a `Secret` or a `ConfigMap` and ensure that it is
being loaded by `${DEPLOY_NAME}/manifest/neutron/kustomize.yaml`

Then you would edit `${DEPLOY_NAME}/neutron/values.yaml` and add something
like:

```yaml
pod:
  mounts:
    neutron_server:
      neutron_server:
        volumeMounts:
          - mountPath: /etc/neutron/neutron.conf.d/myfile.conf  # file which will be loaded
            name: mysection  # volume name from below
            subPath: myfile.conf  # key in the Secret or ConfigMap from the volume below
            readOnly: true
        volumes:
          - name: mysection # volume name above
            secret:
              secretName: mysecret  # name of secret
```

See [Kubernetes Volumes](https://kubernetes.io/docs/concepts/storage/volumes/) for more details.
