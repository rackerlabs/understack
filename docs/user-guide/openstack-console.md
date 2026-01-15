# Graphical Console

Accessing physical server's baremetal console may be required in case of emergencies.
Here is how to access it.

## Pre-requisites

1. Knowledge of **Baremetal node UUID** - the console is for a physical
   baremetal node rather than a server (aka Nova instance).
2. `openstack` CLI with baremetal plugin
3. Web Browser

## Steps

1. Obtain the baremetal node UUID. Example:

    ```text
    ❯ openstack server list
    +--------------------------------------+---------------+--------+-------------------------------+-----------------+-----------+
    | ID                                   | Name          | Status | Networks                      | Image           | Flavor    |
    +--------------------------------------+---------------+--------+-------------------------------+-----------------+-----------+
    | de556585-8710-4ec3-b9d7-daef148f2102 | test-server-5 | ACTIVE | mareks-svm-test4=192.168.0.14 | My-Ubuntu-24.04 | gp2.small |
    +--------------------------------------+---------------+--------+-------------------------------+-----------------+-----------+

    ❯ openstack server show test-server-5 -c OS-EXT-SRV-ATTR:hypervisor_hostname
    +-------------------------------------+--------------------------------------+
    | Field                               | Value                                |
    +-------------------------------------+--------------------------------------+
    | OS-EXT-SRV-ATTR:hypervisor_hostname | 2fb79bdb-c925-4701-b304-b3768deeb85e |
    +-------------------------------------+--------------------------------------+
    ```

    In the above output, the `2fb79bdb-c925-4701-b304-b3768deeb85e` is the one we
    are interested in.

1. Enable the console

    ```text
    ❯ openstack baremetal node console enable 2fb79bdb-c925-4701-b304-b3768deeb85e
    ```

1. Obtain the console address

    ```text
    ❯ openstack baremetal node console show 2fb79bdb-c925-4701-b304-b3768deeb85e
    +-----------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
    | Field           | Value                                                                                                                                                                                                 |
    +-----------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
    | console_enabled | True                                                                                                                                                                                                  |
    | console_info    | {'type': 'vnc', 'url': 'https://console-0.dev.undercloud.rackspace.net/vnc.html?path=websockify%3Fnode%3D055818eb-7de7-43f5-b747-e8704ad7db45%26token%3DSBSyV8pUQoFaAPESACOskV2IwmZo9fqQOWPf3GmP3pQ'} |
    +-----------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
    ```

    If the console is not ready, you may receive following output:

    ```text
    ❯ openstack baremetal node console show Dell-J2GSW04
    +-----------------+-------+
    | Field           | Value |
    +-----------------+-------+
    | console_enabled | False |
    | console_info    | None  |
    +-----------------+-------+
    ```

    Just wait few seconds and try again. If the issue is persistent, contact support.

    > [!INFO] URL can be extracted with:
    > `openstack baremetal node console show <ID> -c console_info -f json | jq -r .console_info.url`

1. Open the provided URL in your browser.
1. Click "connect" and you should be presented with a console within few seconds.
