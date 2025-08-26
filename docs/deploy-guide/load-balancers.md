# Load Balancer Configuration

If you decide to use Octavia Load Balancers there are some one-time, post-install
steps to be completed before load balancers can be used.

## Create security groups and their rules

``` bash
openstack security group create lb-mgmt-sec-grp
openstack security group rule create --protocol icmp lb-mgmt-sec-grp
openstack security group rule create --protocol tcp --dst-port 22 lb-mgmt-sec-grp
openstack security group rule create --protocol tcp --dst-port 9443 lb-mgmt-sec-grp
openstack security group create lb-health-mgr-sec-grp
openstack security group rule create --protocol udp --dst-port 5555 lb-health-mgr-sec-grp
```

## Create a network

During the execution of the below command, please save the of BRNAME and MGMT_PORT_MAC in a notepad for further reference.

``` bash
OCTAVIA_MGMT_SUBNET=172.16.0.0/12
OCTAVIA_MGMT_SUBNET_START=172.16.0.100
OCTAVIA_MGMT_SUBNET_END=172.16.31.254
OCTAVIA_MGMT_PORT_IP=172.16.0.2

openstack network create lb-mgmt-net
openstack subnet create --subnet-range $OCTAVIA_MGMT_SUBNET --allocation-pool \
  start=$OCTAVIA_MGMT_SUBNET_START,end=$OCTAVIA_MGMT_SUBNET_END \
  --network lb-mgmt-net lb-mgmt-subnet

SUBNET_ID=$(openstack subnet show lb-mgmt-subnet -f value -c id)
PORT_FIXED_IP="--fixed-ip subnet=$SUBNET_ID,ip-address=$OCTAVIA_MGMT_PORT_IP"

MGMT_PORT_ID=$(openstack port create --security-group \
  lb-health-mgr-sec-grp --device-owner Octavia:health-mgr \
  --host=$(hostname) -c id -f value --network lb-mgmt-net \
PORT_FIXED_IP octavia-health-manager-listen-port)

MGMT_PORT_MAC=$(openstack port show -c mac_address -f value \
MGMT_PORT_ID)
```


``` bash
OSH_LB_SUBNET="172.31.0.0/24"
OSH_LB_SUBNET_START="172.31.0.2"
OSH_LB_SUBNET_END="172.31.0.200"

openstack network create lb-mgmt-net -f value -c id
openstack subnet create --subnet-range $OSH_LB_SUBNET --allocation-pool start=$OSH_LB_SUBNET_START,end=$OSH_LB_SUBNET_END --network lb-mgmt-net lb-mgmt-subnet -f value -c id
openstack security group create lb-mgmt-sec-grp
openstack security group rule create --protocol icmp lb-mgmt-sec-grp
openstack security group rule create --protocol tcp --dst-port 22 lb-mgmt-sec-grp
openstack security group rule create --protocol tcp --dst-port 9443 lb-mgmt-sec-grp

# Create security group for Octavia health manager
openstack security group create lb-health-mgr-sec-grp
openstack security group rule create --protocol udp --dst-port 5555 lb-health-mgr-sec-grp
```

``` bash
node=1327172-hp1
PORTNAME=octavia-health-manager-port-1327172-hp1

openstack port create --security-group lb-health-mgr-sec-grp --device-owner Octavia:health-mgr --host=$node -c id -f value --network lb-mgmt-net $PORTNAME
IP=$(openstack port show $PORTNAME -c fixed_ips -f value | awk -F',' '{print $1}' | awk -F'=' '{print $2}' | tr -d \')
echo $IP
```

``` bash
NETWORK_NODES=$(kubectl get nodes -l openstack-network-node=enabled -o name | awk -F"/" '{print $2}')
for node in $NETWORK_NODES; do 

done

```