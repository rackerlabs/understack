# Operating System Images

Operating System images are managed by the OpenStack Glance service. The
`openstack image` command is part of the OpenStack Client (OSC) and allows
users to interact with images within an OpenStack cloud. This documentation
covers how to list available images, find specific images, and upload new
images using the `openstack` command.

## Prerequisites

Before using the `openstack` command, ensure that the OpenStack Client is
installed and properly configured. You should have sourced your OpenStack RC
file or configured your `clouds.yaml` to set the necessary environment
variables for authentication.

## Listing Images

To view all the available images within your OpenStack project, use the following command:

```bash
openstack image list
```

This command returns a list of images, including details such as the image ID,
name, status, and visibility.

```bash title="Example Output"
+--------------------------------------+------------------+--------+
| ID                                   | Name             | Status |
+--------------------------------------+------------------+--------+
| 9b6d68e8-4c4a-4f5d-a4c1-bc43e0e4c123 | Ubuntu 24.04 LTS | active |
| 3f7c7b28-5c57-483a-9f29-ec041c798765 | CentOS 9         | active |
+--------------------------------------+------------------+--------+
```

### Finding a Specific Image

To find a specific image by its name, you can use the openstack image list command
with the --name filter:

```bash
openstack image list --name <image_name>
```

Replace <image_name> with the name of the image you want to find. For example, to
find an image named "Ubuntu 24.04 LTS":

```bash
openstack image list --name "Ubuntu 20.04 LTS"
```

You can filter the list by using the `--property key=value` or `--tag tag`
arguments as well.

```bash
openstack image list --property os_distro=ubuntu
```

## Adding an Image

You can upload your own image to provision onto systems assuming they are
whole disk images. You must know some metadata about the image you are
uploading and no verification of the metadata will be performed. For
example to upload an image based on Ubuntu 24.04 you could run:

```bash
openstack image create 'My-Ubuntu-24.04' \
  --disk-format qcow2 \
  --property os_distro=ubuntu \
  --property os_version=24.04 \
  --file=/path/to/image.qcow2
```

Explanation:

* `--disk-format qcow2`: Specifies the disk format of the image (e.g., `qcow2`, `raw`, `vmdk`).
* `--file /path/to/image.qcow2`: Specifies the path to the image file on your local machine.
* `--public`: (Optional) Makes the image publicly accessible. Remove this flag to keep the image private to your project.

## Additional Information

For more detailed information on the openstack image command and its various
options, refer to the official OpenStack documentation:

* [OpenStack CLI Command Reference - Image](https://docs.openstack.org/python-openstackclient/latest/cli/command-objects/image.html)
* [OpenStack Image Service (Glance) Documentation](https://docs.openstack.org/glance/latest/)
