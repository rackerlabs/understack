# Debugging Neutron

## Debugging ML2

To debug ML2 and see the messages that are flowing into the ML2
mechanism you can add the following snippet into your `neutron.yaml`
for your environment.

```yaml
conf:
  plugins:
    ml2_conf:
      ml2:
        # this line just aims to add 'logger' but its
        # replacing so you'll need to pay attention
        # to any changes your environment might have
        # from the default
        mechanism_drivers: "logger,understack,ovn"
  logging:
    loggers:
      # for 'keys' we are attempt to append 'mechanism_logger'
      # but the way YAML are merged you will need to include
      # all other items in the list here as well.
      keys:
        - ...
        - mechanism_logger
    logger_mechanism_logger:
      level: DEBUG
      handlers: stdout
      qualname: mechanism_logger
```

Once you deploy this the `neutron-server` pod will now log everything that the
ML2 drivers receive. The log line will have `called with network settings` in it.
That message will be prefixed with the ML2 method name like `create_network_postcommit`.
