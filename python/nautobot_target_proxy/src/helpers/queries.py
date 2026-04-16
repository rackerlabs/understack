OOB_TARGET_QUERY = """
{
  interfaces(mgmt_only: true, name: ["iDRAC", "iLO"]) {
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
