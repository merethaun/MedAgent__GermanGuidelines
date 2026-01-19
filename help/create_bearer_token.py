# call with: python create_bearer_token.py -u name -p password

import argparse
import getpass
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def _post_form(url: str, data: dict[str, str], timeout: int) -> dict:
    body = urlencode(data).encode("utf-8")
    req = Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except HTTPError as e:
        raw = e.read().decode("utf-8") if e.fp else str(e)
        raise RuntimeError(f"HTTP {e.code} from Keycloak: {raw}") from e
    except URLError as e:
        raise RuntimeError(f"Failed to reach Keycloak: {e}") from e


def main() -> int:
    p = argparse.ArgumentParser(description="Get a Keycloak access token (password grant).")
    p.add_argument("--base-url", default="http://localhost:8080", help="Keycloak base URL")
    p.add_argument("--realm", default="medagent", help="Realm name")
    p.add_argument("--client-id", default="medagent-frontend", help="Client ID")
    p.add_argument("--username", "-u", required=True, help="Username")
    p.add_argument("--password", "-p", default=None, help="Password (discouraged; will prompt if omitted)")
    p.add_argument("--timeout", type=int, default=10, help="Timeout seconds")
    p.add_argument("--print-json", action="store_true", help="Print full token JSON instead of only access token")
    args = p.parse_args()
    
    password = args.password or getpass.getpass("Keycloak password: ")
    
    token_url = f"{args.base_url.rstrip('/')}/realms/{args.realm}/protocol/openid-connect/token"
    payload = {
        "client_id": args.client_id,
        "grant_type": "password",
        "username": args.username,
        "password": password,
    }
    
    data = _post_form(token_url, payload, timeout=args.timeout)
    
    if args.print_json:
        print(json.dumps(data, indent=2))
        return 0
    
    access_token = data.get("access_token")
    if not access_token:
        raise RuntimeError(f"No access_token in response: {data}")
    
    print(access_token)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(1)
