import argparse
import ipaddress
import json
import logging
import requests
from pathlib import Path

logging.basicConfig(level=logging.DEBUG)

BASE_URL = "https://api.porkbun.com/api/json/v3"
RETRIEVE_DNS_RECORDS_BY_NAME_SUB_ADDRESS = "/dns/retrieveByNameType"
UPDATE_DNS_RECORDS_BY_NAME_SUB_ADDRESS = "/dns/editByNameType"
DEFAULT_TTL = "600"
IPV4_MIRROR = "https://api.ipify.org"


def load_config_from_json(path: Path) -> dict[str, str]:
    with open(path, "r") as f:
        return json.load(f)


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


def get_ipv4_records(
    subdomain: str, domain: str, headers: dict, payload: dict
) -> list[ipaddress.IPv4Address]:
    try:
        response = requests.post(
            BASE_URL
            + RETRIEVE_DNS_RECORDS_BY_NAME_SUB_ADDRESS
            + "/"
            + domain
            + "/A/"
            + subdomain,
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        json = response.json()
        if json["status"] != "SUCCESS":
            raise Exception(
                f"Something went wrong when getting the A record for {subdomain}.{domain}: {response.text}"
            )
        return [ipaddress.IPv4Address(record["content"]) for record in json["records"]]
    except requests.exceptions.HTTPError as e:
        raise Exception(f"HTTP Error occurred: {e} Response content: {response.text}")


def set_ipv4_records(
    ip_address: ipaddress.IPv4Address,
    subdomain: str,
    domain: str,
    headers: dict,
    payload: dict,
):
    try:
        updated_payload = {
            "secretapikey": payload["secretapikey"],
            "apikey": payload["apikey"],
            "content": ip_address.exploded,
            "ttl": DEFAULT_TTL,
        }
        response = requests.post(
            BASE_URL
            + UPDATE_DNS_RECORDS_BY_NAME_SUB_ADDRESS
            + "/"
            + domain
            + "/A/"
            + subdomain,
            headers=headers,
            json=updated_payload,
        )
        response.raise_for_status()
        json = response.json()
        if json["status"] != "SUCCESS":
            raise Exception(
                f"Something went wrong when setting the A record for {subdomain}.{domain} to {ipaddress}: {response.text}"
            )
        return [ipaddress.IPv4Address(record["content"]) for record in json["records"]]
    except requests.exceptions.HTTPError as e:
        raise Exception(f"HTTP Error occurred: {e} Response content: {response.text}")


def get_public_ipv4() -> ipaddress.IPv4Address:
    try:
        response = requests.get(IPV4_MIRROR, timeout=5)
        response.raise_for_status()
        return ipaddress.IPv4Address(response.text.strip())
    except requests.exceptions.HTTPError as e:
        raise Exception(f"HTTP Error occurred: {e} Response content: {response.text}")


def main() -> int:
    args = parse_args()
    config = load_config_from_json(args.api_json)

    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
    }
    payload = {
        "secretapikey": str(config["secretapikey"]),
        "apikey": str(config["apikey"]),
    }

    current_ipv4_records = get_ipv4_records(
        args.subdomain, args.domain, headers, payload
    )
    logging.info(f"Current IPv4 records: {current_ipv4_records}")

    public_ipv4 = get_public_ipv4()
    logging.info(f"Current public IPv4 address: {public_ipv4}")
    if public_ipv4 in current_ipv4_records:
        logging.info(
            f"{current_ipv4_records}->{public_ipv4} Record already up to date, exiting"
        )
        return 0

    set_ipv4_records(public_ipv4, args.subdomain, args.domain, headers, payload)
    return 0


if __name__ == "__main__":
    main()
