#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
import tempfile
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


def main():
    parser = argparse.ArgumentParser(
        description="Fetch GitHub Actions logs and extract server data"
    )
    parser.add_argument("url", help="GitHub Actions job URL")
    parser.add_argument(
        "--token", help="GitHub personal access token (or set GITHUB_TOKEN env var)"
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
        print(f"\nGrafana logs URL:\n{grafana_url}")

    return data


if __name__ == "__main__":
    main()
