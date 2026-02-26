#!/usr/bin/env python3
import argparse
import json
import os
import re
import ssl
import sys
import tempfile
import urllib.parse
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def parse_github_url(url):
    """Extract owner, repo, run_id, and job_id from GitHub Actions URL."""
    pattern = r"github\.com/([^/]+)/([^/]+)/actions/runs/(\d+)/job/(\d+)"
    match = re.search(pattern, url)
    if not match:
        raise ValueError("Invalid GitHub Actions URL format")
    return match.groups()


def fetch_job_logs(owner, repo, job_id, token=None):
    """Fetch logs from GitHub Actions job."""
    from urllib.request import HTTPRedirectHandler, build_opener, HTTPSHandler

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    api_url = f"https://api.github.com/repos/{owner}/{repo}/actions/jobs/{job_id}/logs"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "gh-log-fetcher",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = Request(api_url, headers=headers)
    opener = build_opener(NoRedirect, HTTPSHandler)

    try:
        with opener.open(req) as response:
            return response.read().decode("utf-8")
    except HTTPError as e:
        if e.code == 302:
            redirect_url = e.headers.get("Location")
            if not redirect_url:
                print("Error fetching logs: missing redirect URL", file=sys.stderr)
                sys.exit(1)
            with urlopen(redirect_url) as response:
                return response.read().decode("utf-8")
        print(f"Error fetching logs: {e.code} {e.reason}", file=sys.stderr)
        sys.exit(1)


def extract_server_data(log_content):
    """Extract server instance ID, name, and network ID from logs."""
    data = {}

    # Extract timestamps
    timestamp_pattern = r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z)"
    timestamps = re.findall(timestamp_pattern, log_content)
    if timestamps:
        data["start_timestamp"] = timestamps[0]
        data["end_timestamp"] = timestamps[-1]

    # Find POST request to create server and extract nova hostname
    post_pattern = r"POST https://nova\.([^/]+)/v2\.1/servers.*?-d \'({.*?})\'"
    post_match = re.search(post_pattern, log_content, re.DOTALL)

    if post_match:
        nova_host = post_match.group(1)
        env_map = {
            "dev.undercloud.rackspace.net": "bravo-uc-iad3-dev",
            "staging.undercloud.rackspace.net": "charlie-uc-iad3-staging",
            "prod.undercloud.rackspace.net": "delta-uc-dfw3-prod",
            "rxdb-lab.undercloud.rackspace.net": "echo-uc-iad3-rxdb-lab",
        }
        data["k8s_cluster"] = env_map.get(nova_host, "delta-uc-dfw3-prod")

        try:
            request_body = json.loads(post_match.group(2))
            data["server_name"] = request_body.get("server", {}).get("name")
            networks = request_body.get("server", {}).get("networks", [])
            if networks:
                data["network_id"] = networks[0].get("uuid")
        except json.JSONDecodeError:
            pass

    # Find server ID from location header in response
    location_pattern = r"location: https://nova\.[^/]+/v2\.1/servers/([a-f0-9-]+)"
    location_match = re.search(location_pattern, log_content, re.IGNORECASE)
    if location_match:
        data["server_id"] = location_match.group(1)

    return data


def fetch_grafana_logs(
    cluster,
    search_id,
    start_timestamp,
    end_timestamp,
    token,
    statefulset=None,
    deployment=None,
):
    """Fetch logs from Grafana Loki."""
    if statefulset:
        query = f'{{k8s_cluster_name="{cluster}", k8s_statefulset_name="{statefulset}"}} |~ "(?i){search_id}"'
    elif deployment:
        query = f'{{k8s_cluster_name="{cluster}", k8s_deployment_name="{deployment}"}} |~ "(?i){search_id}"'
    else:
        raise ValueError("Either statefulset or deployment must be specified")

    # Convert ISO timestamps to nanoseconds
    start_dt = datetime.fromisoformat(start_timestamp.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(end_timestamp.replace("Z", "+00:00"))
    start_ns = int(start_dt.timestamp() * 1_000_000_000)
    end_ns = int(end_dt.timestamp() * 1_000_000_000)

    params = urllib.parse.urlencode(
        {
            "query": query,
            "start": start_ns,
            "end": end_ns,
            "limit": 5000,
            "direction": "forward",
        }
    )

    url = f"https://grafana.core.ord.pvceng.rax.io/api/datasources/proxy/uid/ab332d05-8028-40de-a9d6-522b8926cf2a/loki/api/v1/query_range?{params}"

    req = Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        with urlopen(req, context=ctx) as response:
            return json.loads(response.read())
    except HTTPError as e:
        error_body = e.read().decode("utf-8")
        raise Exception(f"HTTP {e.code}: {error_body}")


def print_grafana_logs(grafana_logs, header):
    """Print log lines from Grafana logs."""
    print(f"\n{'=' * 80}")
    print(header)
    print("=" * 80)
    if not grafana_logs or grafana_logs.get("status") != "success":
        print("No logs available")
        return

    for stream in grafana_logs.get("data", {}).get("result", []):
        for value in stream.get("values", []):
            if len(value) > 1:
                timestamp_ns = int(value[0])
                timestamp_s = timestamp_ns / 1_000_000_000
                dt = datetime.fromtimestamp(timestamp_s)
                time_str = dt.strftime("%H:%M:%S.%f")[:-3]
                log_line = value[1]
                log_line = log_line.replace(" ERROR ", " \033[31mERROR\033[0m ")
                log_line = log_line.replace(" WARNING ", " \033[33mWARNING\033[0m ")
                log_line = log_line.replace(" INFO ", " \033[32mINFO\033[0m ")
                print(f"\033[36m{time_str}\033[0m {log_line}")


def extract_baremetal_node_id(grafana_logs):
    """Extract baremetal_node_id from Grafana logs."""
    if not grafana_logs or grafana_logs.get("status") != "success":
        return None

    pattern = r"Claim successful on node ([a-f0-9-]+)"
    for stream in grafana_logs.get("data", {}).get("result", []):
        for value in stream.get("values", []):
            log_line = value[1] if len(value) > 1 else ""
            match = re.search(pattern, log_line)
            if match:
                return match.group(1)
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Fetch GitHub Actions logs and extract server data"
    )
    parser.add_argument("url", help="GitHub Actions job URL")
    parser.add_argument(
        "--token", help="GitHub personal access token (or set GITHUB_TOKEN env var)"
    )
    parser.add_argument(
        "--grafana-token", help="Grafana API token (or set GRAFANA_TOKEN env var)"
    )
    args = parser.parse_args()

    # Parse URL
    owner, repo, run_id, job_id = parse_github_url(args.url)
    print(f"Fetching logs for {owner}/{repo} job {job_id}...")

    # Fetch logs
    token = args.token or os.getenv("GITHUB_TOKEN")
    logs = fetch_job_logs(owner, repo, job_id, token)

    # Save to temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, prefix="gh-job-"
    ) as f:
        f.write(logs)
        temp_path = f.name

    print(f"Logs saved to: {temp_path}")

    # Extract data
    data = extract_server_data(logs)

    print("\nExtracted data:")
    print(json.dumps(data, indent=2))

    # Generate Grafana URL
    if all(
        k in data
        for k in ["server_id", "start_timestamp", "end_timestamp", "k8s_cluster"]
    ):
        # Convert ISO timestamps to Unix milliseconds
        start_dt = datetime.fromisoformat(
            data["start_timestamp"].replace("Z", "+00:00")
        )
        end_dt = datetime.fromisoformat(data["end_timestamp"].replace("Z", "+00:00"))
        start_ms = int(start_dt.timestamp() * 1000)
        end_ms = int(end_dt.timestamp() * 1000)

        cluster = data["k8s_cluster"]
        grafana_url = (
            f"https://grafana.core.ord.pvceng.rax.io/a/grafana-lokiexplore-app/explore/"
            f"k8s_cluster_name/{cluster}/logs?patterns=%5B%5D"
            f"&from={start_ms}&to={end_ms}"
            f"&var-lineFormat=&var-ds=ab332d05-8028-40de-a9d6-522b8926cf2a"
            f"&var-filters=k8s_cluster_name%7C%3D%7C{cluster}"
            f"&var-filters=k8s_statefulset_name%7C%3D%7Cnova-compute-ironic"
            f"&var-fields=&var-levels=&var-metadata=&var-jsonFields=&var-patterns="
            f"&var-lineFilterV2=&var-lineFilters=caseInsensitive,0%7C__gfp__~%7C{data['server_id']}"
            f"&displayedFields=%5B%5D&urlColumns=%5B%5D&visualizationType=%22logs%22"
            f"&timezone=browser&var-all-fields=&userDisplayedFields=false"
            f"&prettifyLogMessage=false&sortOrder=%22Ascending%22&wrapLogMessage=true"
        )
        print(f"\nGrafana: nova-compute-ironic logs:\n{grafana_url}")

        # Fetch Grafana logs if token provided
        grafana_token = args.grafana_token or os.getenv("GRAFANA_TOKEN")
        if grafana_token:
            print("\nFetching logs from Grafana...")
            try:
                grafana_data = fetch_grafana_logs(
                    cluster,
                    data["server_id"],
                    data["start_timestamp"],
                    data["end_timestamp"],
                    grafana_token,
                    statefulset="nova-compute-ironic",
                )

                # Save Grafana logs
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".json", delete=False, prefix="grafana-logs-"
                ) as f:
                    json.dump(grafana_data, f, indent=2)
                    print(f"Grafana logs saved to: {f.name}")

                print_grafana_logs(grafana_data, "nova-compute-ironic")

                # Extract baremetal_node_id
                baremetal_node_id = extract_baremetal_node_id(grafana_data)
                if baremetal_node_id:
                    data["baremetal_node_id"] = baremetal_node_id

                    # Generate ironic-conductor Grafana URL
                    ironic_url = (
                        f"https://grafana.core.ord.pvceng.rax.io/a/grafana-lokiexplore-app/explore/"
                        f"k8s_cluster_name/{cluster}/logs?patterns=%5B%5D"
                        f"&from={start_ms}&to={end_ms}"
                        f"&var-lineFormat=&var-ds=ab332d05-8028-40de-a9d6-522b8926cf2a"
                        f"&var-filters=k8s_cluster_name%7C%3D%7C{cluster}"
                        f"&var-filters=k8s_statefulset_name%7C%3D%7Cironic-conductor"
                        f"&var-fields=&var-levels=&var-metadata=&var-jsonFields=&var-patterns="
                        f"&var-lineFilterV2=&var-lineFilters=caseInsensitive,0%7C__gfp__~%7C{baremetal_node_id}"
                        f"&displayedFields=%5B%5D&urlColumns=%5B%5D&visualizationType=%22logs%22"
                        f"&timezone=browser&var-all-fields=&userDisplayedFields=false"
                        f"&prettifyLogMessage=false&sortOrder=%22Ascending%22&wrapLogMessage=true"
                    )
                    print(f"\nGrafana: ironic-conductor logs:\n{ironic_url}")

                    # Fetch ironic-conductor logs
                    print("\nFetching ironic-conductor logs...")
                    try:
                        ironic_data = fetch_grafana_logs(
                            cluster,
                            baremetal_node_id,
                            data["start_timestamp"],
                            data["end_timestamp"],
                            grafana_token,
                            statefulset="ironic-conductor",
                        )
                        with tempfile.NamedTemporaryFile(
                            mode="w",
                            suffix=".json",
                            delete=False,
                            prefix="ironic-logs-",
                        ) as f:
                            json.dump(ironic_data, f, indent=2)
                            print(f"Ironic-conductor logs saved to: {f.name}")

                        print_grafana_logs(ironic_data, "ironic-conductor")
                    except Exception as e:
                        print(
                            f"Error fetching ironic-conductor logs: {e}",
                            file=sys.stderr,
                        )

                    # Generate neutron-server Grafana URL
                    neutron_url = (
                        f"https://grafana.core.ord.pvceng.rax.io/a/grafana-lokiexplore-app/explore/"
                        f"k8s_cluster_name/{cluster}/logs?patterns=%5B%5D"
                        f"&from={start_ms}&to={end_ms}"
                        f"&var-lineFormat=&var-ds=ab332d05-8028-40de-a9d6-522b8926cf2a"
                        f"&var-filters=k8s_cluster_name%7C%3D%7C{cluster}"
                        f"&var-filters=k8s_deployment_name%7C%3D%7Cneutron-server"
                        f"&var-fields=&var-levels=&var-metadata=&var-jsonFields=&var-patterns="
                        f"&var-lineFilterV2=&var-lineFilters=caseInsensitive,0%7C__gfp__~%7C{baremetal_node_id}"
                        f"&displayedFields=%5B%5D&urlColumns=%5B%5D&visualizationType=%22logs%22"
                        f"&timezone=browser&var-all-fields=&userDisplayedFields=false"
                        f"&prettifyLogMessage=false&sortOrder=%22Ascending%22&wrapLogMessage=true"
                    )
                    print(f"\nGrafana: neutron-server logs:\n{neutron_url}")

                    # Fetch neutron-server logs
                    print("\nFetching neutron-server logs...")
                    try:
                        neutron_data = fetch_grafana_logs(
                            cluster,
                            baremetal_node_id,
                            data["start_timestamp"],
                            data["end_timestamp"],
                            grafana_token,
                            deployment="neutron-server",
                        )
                        with tempfile.NamedTemporaryFile(
                            mode="w",
                            suffix=".json",
                            delete=False,
                            prefix="neutron-logs-",
                        ) as f:
                            json.dump(neutron_data, f, indent=2)
                            print(f"Neutron-server logs saved to: {f.name}")

                        print_grafana_logs(neutron_data, "neutron-server")
                    except Exception as e:
                        print(
                            f"Error fetching neutron-server logs: {e}", file=sys.stderr
                        )
            except Exception as e:
                print(f"Error fetching Grafana logs: {e}", file=sys.stderr)

    return data


if __name__ == "__main__":
    main()
