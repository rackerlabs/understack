# Nautobot

## Nautobot Django shell

You can access the Nautobot Django shell by connecting to the pod and running the
`nautobot-server shell` command.

``` bash
# find one of the nautobot app pods
kubectl get pod -l app.kubernetes.io/component=nautobot-default
NAME                                READY   STATUS    RESTARTS   AGE
nautobot-default-598bddbc79-kbr72   1/1     Running   0          2d4h
nautobot-default-598bddbc79-lnjj6   1/1     Running   0          2d4h
```

``` bash
# use the nautobot-server shell
kubectl exec -it nautobot-default-598bddbc79-kbr72 -- nautobot-server shell
```

## Nautobot GraphQL Queries

### Query for all servers in a specific rack

This queries devices with the role `server` located in rack `rack-123`
and includes the iDRAC/iLO BMC IP address.

``` graphql
query {
  devices(role: "server", rack: "rack-123") {
    id
    name
    interfaces(name: ["iDRAC", "iLO"]) {
      ip_addresses {
        host
      }
    }
  }
}
```

Output example:

``` json title="rack-123-devices-output.json"
{
  "data": {
    "devices": [
      {
        "id": "4933fb3d-aa7c-4569-ae25-0af879a11291",
        "name": "server-1",
        "interfaces": [
          {
            "ip_addresses": [
              {
                "host": "10.0.0.1"
              }
            ]
          }
        ]
      },
      {
        "id": "f6be9302-96b0-47e9-ad63-6056a5e9a8f5",
        "name": "server-2",
        "interfaces": [
          {
            "ip_addresses": [
              {
                "host": "10.0.0.2"
              }
            ]
          }
        ]
      }
    ]
  }
}
```

Some jq to help parse the output:

``` bash
cat rack-123-devices-output.json | jq -r '.data.devices[] | "\(.id) \(.interfaces[0]["ip_addresses"][0]["host"])"'
```

Output:

``` text
4933fb3d-aa7c-4569-ae25-0af879a11291 10.0.0.1
f6be9302-96b0-47e9-ad63-6056a5e9a8f5 10.0.0.2
```
