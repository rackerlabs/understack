import openstack

openstack.enable_logging(debug=True)


def list_projects(conn):
    print("List Projects:")

    for project in conn.identity.projects():
        print(project)


if __name__ == "__main__":
    cloud_connection = openstack.connect(os_cloud="uc-dev-infra")
    list_projects(cloud_connection)
