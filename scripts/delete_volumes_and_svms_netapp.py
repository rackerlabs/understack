#!/usr/bin/env python3

import argparse
import os
import requests
import sys
import urllib3
from requests.auth import HTTPBasicAuth

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def delete_volume(hostname, login, password, project_id):
    """Delete volume named vol_$project_id"""
    volume_name = f"vol_{project_id}"
    url = f"https://{hostname}/api/storage/volumes"

    # First, find the volume by name
    params = {"name": volume_name}
    response = requests.get(
        url, auth=HTTPBasicAuth(login, password), params=params, verify=False
    )

    if response.status_code != 200:
        print(
            f"Error finding volume {volume_name}: {response.status_code} - {response.text}"
        )
        return False

    volumes = response.json().get("records", [])
    if not volumes:
        print(f"Volume {volume_name} not found")
        return False

    volume_uuid = volumes[0]["uuid"]

    # Delete the volume
    delete_url = f"{url}/{volume_uuid}"
    response = requests.delete(
        delete_url, auth=HTTPBasicAuth(login, password), verify=False
    )

    if response.status_code == 202:
        print(f"Volume {volume_name} deletion initiated successfully")
        return True
    else:
        print(
            f"Error deleting volume {volume_name}: {response.status_code} - {response.text}"
        )
        return False


def delete_svm(hostname, login, password, project_id):
    """Delete SVM named os-$project_id"""
    svm_name = f"os-{project_id}"
    url = f"https://{hostname}/api/svm/svms"

    # First, find the SVM by name
    params = {"name": svm_name}
    response = requests.get(
        url, auth=HTTPBasicAuth(login, password), params=params, verify=False
    )

    if response.status_code != 200:
        print(f"Error finding SVM {svm_name}: {response.status_code} - {response.text}")
        return False

    svms = response.json().get("records", [])
    if not svms:
        print(f"SVM {svm_name} not found")
        return False

    svm_uuid = svms[0]["uuid"]

    # Delete the SVM
    delete_url = f"{url}/{svm_uuid}"
    response = requests.delete(
        delete_url, auth=HTTPBasicAuth(login, password), verify=False
    )

    if response.status_code == 202:
        print(f"SVM {svm_name} deletion initiated successfully")
        return True
    else:
        print(
            f"Error deleting SVM {svm_name}: {response.status_code} - {response.text}"
        )
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Delete NetApp ONTAP volume and SVM for a project"
    )
    parser.add_argument("project_id", help="Project ID")

    args = parser.parse_args()

    # Get credentials from environment variables
    hostname = os.getenv("NETAPP_HOST")
    login = os.getenv("NETAPP_LOGIN")
    password = os.getenv("NETAPP_PASSWORD")

    if not hostname or not login or not password:
        print(
            "Error: NETAPP_HOST, NETAPP_LOGIN, and NETAPP_PASSWORD environment variables must be set"
        )
        sys.exit(1)

    print(f"Deleting resources for project: {args.project_id}")
    print(f"Connecting to ONTAP: {hostname}")

    # Delete volume first
    volume_success = delete_volume(hostname, login, password, args.project_id)

    # Delete SVM
    svm_success = delete_svm(hostname, login, password, args.project_id)

    if volume_success and svm_success:
        print("All resources deleted successfully")
        sys.exit(0)
    else:
        print("Some resources failed to delete")
        sys.exit(1)


if __name__ == "__main__":
    main()
