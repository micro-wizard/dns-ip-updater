import argparse
import ipaddress
import json
import logging

import requests

logging.basicConfig(level=logging.DEBUG)

BASE_URL = "https://api.hosting.ionos.com"
ZONES_SUB_ADDRESS = "/dns/v1/zones"
IPV4_MIRROR = "https://api.ipify.org"
IPV6_MIRROR = "https://api64.ipify.org"


def load_config_from_json(path):
    try:
        with open(path, "r") as f:
            data = json.load(f)
            return data
    except Exception as e:
        print(f"Error reading JSON file {path}: {e}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Update DNS record IP to match current public IP."
    )
    parser.add_argument(
        "--subdomain",
        "-s",
        required=True,
        help="The subdomain to update (e.g., 'www').",
    )
    parser.add_argument(
        "--domain",
        "-d",
        required=True,
        help="The domain to update (e.g., 'example.com').",
    )
    parser.add_argument(
        "--api-json",
        "-j",
        required=True,
        help="Path to JSON file containing {'api_key': ..., 'public_prefix_api': ...}.",
    )

    return parser.parse_args()


def get_public_ipv4() -> ipaddress.IPv4Address | None:
    try:
        response = requests.get(IPV4_MIRROR, timeout=5)
        response.raise_for_status()
        return ipaddress.IPv4Address(response.text.strip())
    except Exception:
        return None


def get_public_ipv6() -> ipaddress.IPv6Address | None:
    try:
        response = requests.get(IPV6_MIRROR, timeout=5)
        response.raise_for_status()
        return ipaddress.IPv6Address(response.text.strip())
    except Exception:
        return None


def get_domain_zone_id(domain: str, headers: dict) -> str | None:
    try:
        response = requests.get(BASE_URL + ZONES_SUB_ADDRESS, headers=headers)
        response.raise_for_status()
        json_response = response.json()

        for item in json_response:
            if item["name"] == domain:
                return item["id"]
        return None
    except requests.RequestException:
        return None


def get_records_list_by_zone_id(
    subdomain: str, domain: str, zone_id: str, headers: dict
) -> list[dict] | None:
    params = {"suffix": f"{subdomain}.{domain}", "recordType": "A,AAAA"}
    try:
        response = requests.get(
            BASE_URL + ZONES_SUB_ADDRESS + "/" + zone_id,
            headers=headers,
            params=params,
        )
        response.raise_for_status()
        json_response = response.json()
        return json_response["records"]
    except requests.RequestException:
        return None


def patch_records_with_different_ips(
    records: list[dict],
    ipv4: ipaddress.IPv4Address | None,
    ipv6: ipaddress.IPv6Address | None,
) -> list[dict]:
    new_records = []

    for record in records:

        if record["type"] == "A" and ipv4 is not None:
            if ipaddress.IPv4Address(record["content"]) != ipv4:
                print(f"replacing {record['content']} with {ipv4}")
                new_record = record.copy()
                new_record["content"] = str(ipv4)
                new_records.append(new_record)

        elif record["type"] == "AAAA" and ipv6 is not None:
            if ipaddress.IPv6Address(record["content"]) != ipv6:
                print(f"replacing {record['content']} with {ipv6}")
                new_record = record.copy()
                new_record["content"] = str(ipv6)
                new_records.append(new_record)

    return new_records


def set_new_records(records: list[dict], zone_id: str, headers: dict):
    if len(records) != 0:
        response = requests.patch(
            BASE_URL + ZONES_SUB_ADDRESS + "/" + zone_id,
            headers=headers,
            json=records,
        )
        response.raise_for_status()


def main():
    args = parse_args()
    config = load_config_from_json(args.api_json)
    headers = {
        "accept": "application/json",
        "X-API-Key": f"{config['public_prefix']}.{config['secret']}",
        "Content-Type": "application/json",
    }

    zone_id = get_domain_zone_id(args.domain, headers)
    if zone_id is None:
        raise Exception("Unable to obtain zone id")

    records = get_records_list_by_zone_id(args.subdomain, args.domain, zone_id, headers)
    if records is None:
        raise Exception("Unable to obtain records")

    ipv4 = get_public_ipv4()
    ipv6 = get_public_ipv6()
    if ipv4 is None:
        raise Exception("Unable to obtain ipv4 address")

    new_records = patch_records_with_different_ips(records, ipv4, ipv6)
    set_new_records(new_records, zone_id, headers)


if __name__ == "__main__":
    main()
