// overrides for
// https://github.com/ipxe/ipxe/blob/master/src/config/console.h

/*
 * Send iPXE console output to a remote syslog server.
 *
 * iPXE populates its `syslog` setting from DHCP option 7 (log-server) when
 * present, so the destination is controlled by dnsmasq rather than compiled in.
 * This only covers the window while iPXE itself is running (chainload + boot
 * script execution), which is exactly the boot/cleaning/deploy phase we want
 * visibility into.
 */
#define CONSOLE_SYSLOG
