#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
import tempfile
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

    # Find POST request to create server
    post_pattern = r"POST https://nova\.[^/]+/v2\.1/servers.*?-d \'({.*?})\'"
    post_match = re.search(post_pattern, log_content, re.DOTALL)

    if post_match:
        try:
            request_body = json.loads(post_match.group(1))
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

    return data


if __name__ == "__main__":
    main()
