# Understanding our Secrets

Like all software projects there are username/password combinations
that are used to authenticate connections between different services.
This document aims to disentangle where each one comes from and
how it's consumed.

## MariaDB

To create our MariaDB cluster we create 1 k8s secret with the key
`root-password` which is the password for the `root` user.

Each OpenStack component will have it's own MariaDB user/password
combination. The pattern that this project utilizes for this secret
is `$COMPONENT-db-password`, where the component is lowercase.
So for Keystone the name would be `keystone-db-password`.

## RabbitMQ

Each OpenStack component will have it's own RabbitMQ user/password
combination. The pattern that this project utilizes for this secret
is `$COMPONENT-rabbitmq-password`, where the component is lowercase.
So for Keystone the name would be `keystone-rabbitmq-password`.
