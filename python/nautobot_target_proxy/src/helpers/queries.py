OOB_TARGET_QUERY = """
query OobTargetQuery($understackPartition: [String]) {
  interfaces(
    mgmt_only: true,
    name: ["iDRAC", "iLO"],
    device: {location: {name: $understackPartition}}
  ) {
    device {
      name
      rack {
        name
      }
      id
      cpf_urn
      location {
        name
      }
    }
    ip_addresses {
      host
    }
  }
}
"""
