"""NetSuite/ADP adapters around dlt RESTClient and OAuth2ClientCredentials.

Official endpoint/auth references are linked in Ingestion/README.md.
No login or network request occurs on import. Both extractors are read-only.
"""
import os
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parents[1]


def validate_vendor_setup(kind):
    """Check local settings before dlt wraps generator errors; never log values."""
    requirements = {
        "netsuite": ("NETSUITE_ACCOUNT_ID", "NETSUITE_CLIENT_ID",
                     "NETSUITE_CERTIFICATE_ID", "NETSUITE_PRIVATE_KEY_PATH"),
        "adp": ("ADP_CLIENT_ID", "ADP_CLIENT_SECRET",
                "ADP_CERT_PATH", "ADP_PRIVATE_KEY_PATH"),
    }
    names = requirements[kind]
    missing = [name for name in names
               if not os.environ.get(name, "").strip()
               or os.environ[name].startswith("YOUR_")]
    if missing:
        raise ValueError(
            f"{kind} API access is not configured. Set these application settings "
            f"in main/.env: {', '.join(missing)}. "
            "See Ingestion/README.md for vendor setup. No browser login opens. "
            "To practise without vendor access, use Ingestion/pipeline.yml."
        )
    for name in names:
        if name.endswith("_PATH"):
            credential_file(name)


def required_env(name):
    value = os.environ.get(name)
    if not value or value.startswith("YOUR_"):
        raise ValueError(f"Set {name} in main/.env before using this source.")
    return value


def credential_file(name):
    path = Path(required_env(name)).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    if not path.is_file():
        raise ValueError(f"{name} must point to an existing credential file.")
    return path


def page_size(source, maximum):
    size = source.get("page_size", maximum)
    if type(size) is not int or not 1 <= size <= maximum:
        raise ValueError(f"page_size must be an integer from 1 to {maximum}.")
    return size


class VendorSession(requests.Session):
    """Bound requests to vendor hosts; retry transient read/token failures."""

    def __init__(self, hosts):
        super().__init__()
        self.hosts = set(hosts)
        retry = Retry(
            total=3, backoff_factor=1,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(("GET", "POST")),
            respect_retry_after_header=True,
        )
        self.mount("https://", HTTPAdapter(max_retries=retry))

    def send(self, request, **kwargs):
        parsed = urlsplit(request.url)
        if (parsed.scheme != "https" or parsed.hostname not in self.hosts
                or parsed.port not in (None, 443) or parsed.username or parsed.password):
            raise ValueError("Request must use the configured vendor HTTPS host.")
        kwargs.update(timeout=(10, 60), allow_redirects=False, verify=True)
        response = super().send(request, **kwargs)
        if 300 <= response.status_code < 400:
            response.close()
            raise RuntimeError("Unexpected API redirect; check the vendor endpoint.")
        return response


def token_auth(session, url, build_request):
    """Reuse dlt's token cache/refresh; specialize signing and validation."""
    from dlt.sources.helpers.rest_client.auth import OAuth2ClientCredentials

    class VendorOAuth(OAuth2ClientCredentials):
        def build_access_token_request(self):
            return build_request()

        def parse_access_token(self, payload):
            token = payload.get("access_token") if isinstance(payload, dict) else None
            if not isinstance(token, str) or not token:
                raise ValueError("OAuth response is missing an access token.")
            if str(payload.get("token_type", "Bearer")).lower() != "bearer":
                raise ValueError("OAuth response uses an unsupported token type.")
            return token

        def parse_expiration_in_seconds(self, payload):
            lifetime = int(payload.get("expires_in", 3600))
            if lifetime <= 0:
                raise ValueError("OAuth token has an invalid lifetime.")
            return max(1, lifetime - min(60, lifetime // 2))

    return VendorOAuth(access_token_url=url, session=session)


def netsuite_token_request(host, client_id, certificate_id, key_path):
    """Oracle M2M assertion: PS256, certificate kid, five-minute lifetime."""
    import jwt
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    password = os.environ.get("NETSUITE_PRIVATE_KEY_PASSPHRASE")
    key = load_pem_private_key(
        key_path.read_bytes(), password=password.encode() if password else None,
    )
    now = int(time.time())
    assertion = jwt.encode(
        {"iss": client_id, "scope": ["rest_webservices"],
         "aud": f"https://{host}/services/rest/auth/oauth2/v1/token",
         "iat": now, "exp": now + 300},
        key, algorithm="PS256", headers={"typ": "JWT", "kid": certificate_id},
    )
    return {"data": {
        "grant_type": "client_credentials",
        "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
        "client_assertion": assertion,
    }}


def check_page(response, collection, *, empty_204=False):
    """Never mistake a vendor error/unexpected response for an empty dataset."""
    if response.status_code == 204 and empty_204:
        from dlt.sources.helpers.rest_client.exceptions import IgnoreResponseException

        raise IgnoreResponseException()
    if response.status_code != 200:
        raise RuntimeError(f"API returned HTTP {response.status_code}; check access.")
    payload = response.json()
    if (not isinstance(payload, dict)
            or not isinstance(payload.get(collection), list)
            or any(not isinstance(row, dict) for row in payload[collection])):
        raise ValueError(f"API response must contain a {collection} array of objects.")
    return payload


def netsuite_rows(source):
    """Read an explicitly ordered SuiteQL result; no CRUD API calls."""
    from dlt.sources.helpers.rest_client import RESTClient
    from dlt.sources.helpers.rest_client.paginators import OffsetPaginator

    account = required_env("NETSUITE_ACCOUNT_ID").lower()
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", account):
        raise ValueError("NETSUITE_ACCOUNT_ID must be the account-specific URL prefix.")
    host = f"{account}.suitetalk.api.netsuite.com"
    query = source.get("query", "").strip()
    if not re.match(r"(?i)^select\s", query) or not re.search(r"(?i)\border\s+by\b", query):
        raise ValueError("Use one SELECT query with a unique ORDER BY for stable paging.")
    if ";" in query:
        raise ValueError("Use one SELECT query without a trailing semicolon.")
    size = page_size(source, 1000)
    result_cap = min(100000, 1000 * size)
    client_id = required_env("NETSUITE_CLIENT_ID")
    certificate_id = required_env("NETSUITE_CERTIFICATE_ID")
    key_path = credential_file("NETSUITE_PRIVATE_KEY_PATH")

    with VendorSession([host]) as session:
        auth = token_auth(
            session, f"https://{host}/services/rest/auth/oauth2/v1/token",
            lambda: netsuite_token_request(host, client_id, certificate_id, key_path),
        )
        client = RESTClient(
            base_url=f"https://{host}/services/rest/query/v1/",
            session=session, auth=auth, data_selector="items",
            paginator=OffsetPaginator(
                limit=size, total_path=None, has_more_path="hasMore",
            ),
        )

        def validate(response, *args, **kwargs):
            payload = check_page(response, "items")
            if not isinstance(payload.get("hasMore"), bool):
                raise ValueError("SuiteQL response is missing boolean hasMore.")
            if payload["hasMore"] and not payload["items"]:
                raise ValueError("SuiteQL claims another page but returned no records.")
            if int(payload.get("totalResults", 0)) >= result_cap:
                raise ValueError("SuiteQL result reaches its paging cap; partition the query.")

        count = 0
        for page in client.paginate(
            "suiteql", method="POST", json={"q": query},
            headers={"Prefer": "transient"}, hooks={"response": [validate]},
        ):
            count += len(page)
            if count >= result_cap:
                raise ValueError("SuiteQL result reaches its paging cap; partition the query.")
            yield from page


def adp_worker(record, include_fields):
    identifier = record.get("associateOID")
    if not isinstance(identifier, str) or not identifier:
        raise ValueError("ADP worker is missing associateOID.")
    result = {key: record[key] for key in include_fields if key in record}
    result["id"] = identifier  # Common key for the existing dbt example/tests.
    return result


def adp_rows(source):
    """US ADP Workforce Now workers, client credentials plus mutual TLS."""
    from dlt.sources.helpers.rest_client import RESTClient
    from dlt.sources.helpers.rest_client.paginators import OffsetPaginator

    size = page_size(source, 50)
    fields = source.get("include_fields", ["associateOID", "workerStatus"])
    if not isinstance(fields, list) or any(not isinstance(x, str) for x in fields):
        raise ValueError("include_fields must list top-level worker field names.")
    client_id = required_env("ADP_CLIENT_ID")
    client_secret = required_env("ADP_CLIENT_SECRET")
    cert = credential_file("ADP_CERT_PATH")
    key = credential_file("ADP_PRIVATE_KEY_PATH")
    with VendorSession(["accounts.adp.com", "api.adp.com"]) as session:
        session.cert = (str(cert), str(key))  # Token AND data requests need mTLS.
        auth = token_auth(
            session, "https://accounts.adp.com/auth/oauth/v2/token",
            lambda: {"auth": (client_id, client_secret),
                     "data": {"grant_type": "client_credentials"}},
        )
        client = RESTClient(
            base_url="https://api.adp.com/", session=session, auth=auth,
            data_selector="workers",
            paginator=OffsetPaginator(
                limit=size, offset_param="$skip", limit_param="$top", total_path=None,
            ),
        )
        previous_ids = None
        max_pages = source.get("max_pages", 10000)
        if type(max_pages) is not int or max_pages < 1:
            raise ValueError("max_pages must be a positive integer.")

        def validate(response, *args, **kwargs):
            check_page(response, "workers", empty_204=True)

        for number, page in enumerate(client.paginate(
            "hr/v2/workers", hooks={"response": [validate]},
        ), start=1):
            if number > max_pages:
                raise ValueError("ADP page limit exceeded; check pagination.")
            rows = [adp_worker(row, fields) for row in page]
            ids = tuple(row["id"] for row in rows)
            if ids and ids == previous_ids:
                raise ValueError("ADP repeated a page; check that $skip is supported.")
            previous_ids = ids
            yield from rows
