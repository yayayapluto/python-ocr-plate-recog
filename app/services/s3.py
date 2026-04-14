import hashlib
import hmac
import os
import httpx
from datetime import datetime, timezone


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signing_key(secret: str, date_stamp: str, region: str, service: str) -> bytes:
    k_date = _sign(("AWS4" + secret).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    return _sign(k_service, "aws4_request")


def _sha256hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hmac_hex(key: bytes, msg: str) -> str:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).hexdigest()


def _build_request(data: bytes, filename: str, content_type: str) -> tuple[str, dict, str]:
    """Build the signed PUT request for S3. Returns (url, headers, public_url)."""
    endpoint = os.environ.get("S3_ENDPOINT", "").rstrip("/")
    bucket = os.environ.get("S3_BUCKET", "")
    access_key = os.environ.get("S3_ACCESS_KEY", "")
    secret_key = os.environ.get("S3_SECRET_KEY", "")
    region = os.environ.get("S3_REGION", "us-east-1") or "us-east-1"
    public_base = os.environ.get("S3_PUBLIC_BASE_URL", "").rstrip("/")

    if not all([endpoint, bucket, access_key, secret_key, public_base]):
        raise RuntimeError("S3 environment variables are not fully configured")

    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    host = endpoint
    for prefix in ("https://", "http://"):
        if host.startswith(prefix):
            host = host[len(prefix):]
            break
    host = host.rstrip("/")

    url = f"{endpoint}/{bucket}/{filename}"
    payload_hash = _sha256hex(data)

    signed_headers_map = {
        "content-type": content_type,
        "host": host,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    sorted_keys = sorted(signed_headers_map)
    canonical_headers = "".join(f"{k}:{signed_headers_map[k]}\n" for k in sorted_keys)
    signed_headers = ";".join(sorted_keys)

    canonical_request = "\n".join([
        "PUT",
        f"/{bucket}/{filename}",
        "",
        canonical_headers,
        signed_headers,
        payload_hash,
    ])

    cred_scope = f"{date_stamp}/{region}/s3/aws4_request"
    string_to_sign = "\n".join([
        "AWS4-HMAC-SHA256",
        amz_date,
        cred_scope,
        _sha256hex(canonical_request.encode("utf-8")),
    ])

    sig_key = _signing_key(secret_key, date_stamp, region, "s3")
    signature = _hmac_hex(sig_key, string_to_sign)

    auth_header = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{cred_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )

    headers = {
        "Content-Type": content_type,
        "x-amz-date": amz_date,
        "x-amz-content-sha256": payload_hash,
        "Authorization": auth_header,
        "Content-Length": str(len(data)),
        "User-Agent": "Mozilla/5.0",
    }

    return url, headers, f"{public_base}/{filename}"


async def upload_to_s3_async(
    data: bytes,
    filename: str,
    client: httpx.AsyncClient,
    content_type: str = "image/jpeg",
) -> str:
    """
    Upload bytes to S3-compatible storage using raw AWS Signature V4.
    Uses manual signing to stay compatible with Ceph-based providers (NevaObjects)
    that reject SDK-added headers.

    Accepts a shared AsyncClient (managed by app lifespan) for connection reuse.
    Retries once on transient failure. Returns the public URL.
    Raises RuntimeError if config is missing or both attempts fail.
    """
    url, headers, public_url = _build_request(data, filename, content_type)

    last_err: Exception = RuntimeError("Upload did not attempt")
    for _ in range(2):
        try:
            resp = await client.put(url, content=data, headers=headers)
            if resp.status_code in (200, 201):
                return public_url
            last_err = RuntimeError(f"S3 upload failed ({resp.status_code}): {resp.text}")
        except httpx.RequestError as e:
            last_err = RuntimeError(f"S3 upload request error: {e}")

    raise last_err
