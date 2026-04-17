OOB_TARGET_QUERY = """
query OobTargetQuery($location: [String]) {
  interfaces(
    mgmt_only: true,
    name: ["iDRAC", "iLO"],
    location: $location
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
