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
  --progress \
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

## Talos Linux

You can use [Talos Linux][talos] in Understack.

Using the [Talos image factory][talos-image-factory] to create the image:

* Under `Hardware Type` choose `Cloud Server` and hit next
* Choose the version and hit next
* Choose `OpenStack` for the Cloud provider and hit next
* Choose your machine architecture - in our case it's `amd64` - and hit next
* Choose system extensions and drivers you may need. In our case we want the `amd-ucode` extension. Then hit next.
* Choose any customizations you may need. Understack works with the defaults. Then hit next.
* On this page you can download The disk image for example `openstack-amd64.raw.xz`

We can now take the raw image and add it to glance to make it available for new server builds:

``` bash
openstack image create --public --disk-format raw --file openstack-amd64.raw 'Talos 1.10.0'
```

Ensure the image has config drive as mandatory:

``` bash
openstack image set --property img_config_drive='mandatory' $NEW_IMAGE_UUID
```

[talos]: <https://www.talos.dev/>
[talos-image-factory]: <https://factory.talos.dev/>

## VMware ESXi

The VMware ESXi installer can be made into an image that can be booted on a machine.
It will not work directly but instead must be converted using the [esxi-img][esxi-img]
utility. To start you will need the VMware ESXi ISO from VMware.

<!-- markdownlint-capture -->
<!-- markdownlint-disable MD046 -->
!!! tip

    You can store the ISO in glance so that you don't have to find it on VMware's
    website again.

    ```bash
    openstack image create \
      --container-format bare \
      --disk-format raw \
      --private \
      --file ~/Downloads/VMware-VMvisor-Installer-8.0U3-24022510.x86_64.iso \
      'ESXi 8.0u3 ISO'
    ```

    Then you can fetch it later.

    ```bash
    openstack image save --file esxi-80u3.iso 'ESXi 8.0u3 ISO'
    ```
<!-- markdownlint-restore -->

If you have [uv][uv] installed then you can use `uvx` to
run it. The following will produce a converted image that can be uploaded to
glance and booted.

```bash
uvx esxi-img gen-img esxi-80u3.iso esxi-80u3.raw
```

To upload it to glance run the following:

```bash
openstack image create \
  --container-format bare \
  --disk-format raw \
  --public \
  --file esxi-80u3.raw \
  --property img_config_drive=mandatory \
  'ESXi 8.0u3'
```

[esxi-img]: <https://github.com/rackerlabs/esxi-img>
[uv]: <https://docs.astral.sh/uv>
