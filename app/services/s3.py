import hashlib
import hmac
import os
import urllib.request
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


def upload_to_s3(data: bytes, filename: str, content_type: str = "image/jpeg") -> str:
    """
    Upload bytes to S3-compatible storage using raw AWS Signature V4.
    Uses the same signing approach as the Go implementation to stay compatible
    with Ceph-based providers (NevaObjects) that reject SDK-added headers.

    Returns the public URL of the uploaded object.
    Raises RuntimeError if S3 config is missing or upload fails.
    """
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

    # Strip scheme manually to stay compatible across Python versions.
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

    req = urllib.request.Request(url, data=data, method="PUT")
    req.add_header("Content-Type", content_type)
    req.add_header("x-amz-date", amz_date)
    req.add_header("x-amz-content-sha256", payload_hash)
    req.add_header("Authorization", auth_header)
    req.add_header("Content-Length", str(len(data)))
    req.add_header("User-Agent", "Mozilla/5.0")

    try:
        with urllib.request.urlopen(req) as resp:
            if resp.status not in (200, 201):
                raise RuntimeError(f"S3 upload returned status {resp.status}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"S3 upload failed ({e.code}): {body}") from e

    return f"{public_base}/{filename}"
