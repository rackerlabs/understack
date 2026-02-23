// overrides for
// https://github.com/ipxe/ipxe/blob/master/src/config/general.h

/* commands */
#define PING_CMD
#define NEIGHBOUR_CMD /* arp inspections */
#define TIME_CMD      /* Measure time taken to execute cmd */
#define NSLOOKUP_CMD  /* dns */
#define IPSTAT_CMD
#undef IBMGMT_CMD     /* disable Infiniband */
#undef FCMGMT_CMD     /* disable Fibre Channel */
#undef SANBOOT_CMD    /* disable SAN cmds */
#undef VNIC_IPOIB     /* disable Infiniband virtual NIC */

/* disable wifi boot */
#undef CRYPTO_80211_WEP
#undef CRYPTO_80211_WPA
#undef CRYPTO_80211_WPA2

/* protocols */
#undef NET_PROTO_IPV6     /* IPv6 protocol */
#undef NET_PROTO_LACP     /* Link Aggregation control protocol */
#undef NET_PROTO_EAPOL    /* EAP over LAN protocol */
#undef NET_PROTO_FCOE     /* disable Fibre Channel over Ethernet */
