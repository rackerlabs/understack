# Overview

The workflow templates in this folder are designed to create device interfaces in Nautobot based on Redfish information retrieved from devices using BMC credentials.

The process begins when a sensor detects updates to Nautobot BMC interfaces, prompting the get-bmc-creds action to fetch the necessary BMC credentials. This step is crucial as it serves as a prerequisite for the other workflows in this folder. You can find examples of such dependencies in the `deps` folder.

Following this, the sensor initiates the `sync-interfaces-to-nautobot` workflow. This workflow obtains Redfish information from a server and uses it to create new device interfaces in Nautobot.

It is also worth noting that embedded/integrated interfaces are omitted for the purposes of the Undercloud project.

## Servers/BMCs supported
The code utilizes the Sushy library to obtain Redfish information. However, to accommodate older versions of Redfish, several workarounds have been implemented within the code.

It was successfully tested on:
Dell:
 - iDRAC9 with Redfish version 1.17.0
 - iDRAC7 with Redfish version 1.6.0
HP:
 - iLO5 with Redfish version 1.4.0
 - iLO4 with Redfish version 1.0.0
