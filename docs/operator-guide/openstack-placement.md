# Placement

## Query Placement usages

Get an openstack token:

``` bash
TOKEN=$(openstack token issue -f value -c id)
```

Make sure to change the placement url to your own environment:

``` bash
curl -k -H "X-Auth-Token: $TOKEN" https://placement.understack/resource_providers/ | jq
```

Further Placement API information: <https://docs.openstack.org/api-ref/placement/>
