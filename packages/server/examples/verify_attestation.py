#!/usr/bin/env python3
"""Verify a Monteclaude server attestation document.

Standalone script — does NOT require the server codebase. Install deps:

    pip install cbor2 cryptography requests

Usage:

    python verify_attestation.py https://monteclaude.ai
    python verify_attestation.py http://localhost:8001
    python verify_attestation.py http://localhost:8001 --expected-pcr0 aabb...

What this does:
    1. Generates a random nonce and requests GET /api/attestation?nonce=<hex>
    2. Decodes the base64 COSE_Sign1 document
    3. Verifies the certificate chain against the AWS Nitro root CA
    4. Verifies the ECDSA-P384 signature over the attestation payload
    5. Checks nonce freshness (matches what we sent)
    6. Extracts PCR-0 (enclave image hash) and server Ethereum address
    7. Optionally compares PCR-0 against an expected value

Exit codes: 0 = verified, 1 = verification failed, 2 = usage error
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
from datetime import datetime, timezone

import cbor2
import requests
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ec, utils
from cryptography.hazmat.primitives.hashes import SHA256, SHA384


# AWS Nitro Enclaves root certificate fingerprint (SHA-256, colon-separated hex).
# Source: https://docs.aws.amazon.com/enclaves/latest/user/verify-root.html
_AWS_ROOT_CERT_FINGERPRINT = (
    "64:1A:03:21:A3:E2:44:EF:E4:56:46:31:95:D6:06:31:"
    "7E:D7:CD:CC:3C:17:56:E0:98:93:F3:C6:8F:79:BB:5B"
)

# AWS root cert download: https://aws-nitro-enclaves.amazonaws.com/AWS_NitroEnclaves_Root-G1.zip


def _fetch_attestation(server_url: str, nonce_hex: str) -> dict:
    """GET /attestation?nonce=<hex> and return JSON response."""
    url = f"{server_url.rstrip('/')}/api/attestation?nonce={nonce_hex}"
    resp = requests.get(url, timeout=10)
    if resp.status_code != 200:
        print(f"FAIL: Server returned HTTP {resp.status_code}: {resp.text}")
        sys.exit(1)
    return resp.json()


def _decode_cose_sign1(raw: bytes) -> tuple[bytes, bytes, bytes]:
    """Decode COSE_Sign1 → (protected_headers, payload, signature)."""
    decoded = cbor2.loads(raw)
    if not isinstance(decoded, cbor2.CBORTag) or decoded.tag != 18:
        raise ValueError("Not a COSE_Sign1 document (expected CBOR tag 18)")
    arr = decoded.value
    if not isinstance(arr, (list, tuple)) or len(arr) != 4:
        raise ValueError("Malformed COSE_Sign1: expected 4-element array")
    protected = bytes(arr[0]) if not isinstance(arr[0], bytes) else arr[0]
    payload = bytes(arr[2]) if not isinstance(arr[2], bytes) else arr[2]
    signature = bytes(arr[3]) if not isinstance(arr[3], bytes) else arr[3]
    return protected, payload, signature


def _build_sig_structure(protected: bytes, payload: bytes) -> bytes:
    """Build the COSE Sig_structure for Signature1 verification.

    Sig_structure = ["Signature1", protected, external_aad, payload]
    Then CBOR-encode the array.
    """
    return cbor2.dumps(["Signature1", protected, b"", payload])


def _parse_payload(payload_bytes: bytes) -> dict:
    """CBOR-decode the attestation payload and validate required fields."""
    payload = cbor2.loads(payload_bytes)
    if not isinstance(payload, dict):
        raise ValueError("Payload is not a CBOR map")
    required = ("module_id", "timestamp", "digest", "pcrs", "certificate", "cabundle")
    for field in required:
        if field not in payload:
            raise ValueError(f"Missing required field: {field}")
    return payload


def _verify_cert_chain(leaf_der: bytes, cabundle_der: list[bytes]) -> x509.Certificate:
    """Verify the certificate chain from leaf → intermediates → root.

    The cabundle from NSM is ordered: [ROOT, INTERM_1, ..., INTERM_N].
    The leaf certificate is separate (in the `certificate` field).

    Returns the verified leaf certificate.
    Raises ValueError on any verification failure.
    """
    if not cabundle_der:
        raise ValueError("Empty CA bundle")

    # Parse all certificates
    leaf_cert = x509.load_der_x509_certificate(leaf_der)
    ca_certs = [x509.load_der_x509_certificate(der) for der in cabundle_der]

    # Verify root cert fingerprint against known AWS Nitro root
    root_cert = ca_certs[0]
    root_fingerprint = root_cert.fingerprint(SHA256()).hex()
    expected_fingerprint = _AWS_ROOT_CERT_FINGERPRINT.replace(":", "").lower()
    if root_fingerprint != expected_fingerprint:
        raise ValueError(
            f"Root certificate fingerprint mismatch.\n"
            f"  Got:      {root_fingerprint}\n"
            f"  Expected: {expected_fingerprint}\n"
            f"  The root CA does not match the AWS Nitro Enclaves root."
        )

    # Build verification chain: leaf → INTERM_N → ... → INTERM_1 → ROOT
    # cabundle is [ROOT, INTERM_1, ..., INTERM_N], so reverse intermediates
    chain = [leaf_cert] + list(reversed(ca_certs))

    # Verify each cert is signed by the next one in the chain
    for i in range(len(chain) - 1):
        child = chain[i]
        parent = chain[i + 1]

        # Check validity period
        now = datetime.now(timezone.utc)
        if now < child.not_valid_before_utc or now > child.not_valid_after_utc:
            raise ValueError(
                f"Certificate expired or not yet valid: "
                f"{child.subject} (valid {child.not_valid_before_utc} to {child.not_valid_after_utc})"
            )

        # Verify signature: child was signed by parent's private key
        parent_pubkey = parent.public_key()
        try:
            parent_pubkey.verify(
                child.signature,
                child.tbs_certificate_bytes,
                ec.ECDSA(child.signature_hash_algorithm),
            )
        except InvalidSignature:
            raise ValueError(
                f"Certificate chain broken: {child.subject} "
                f"is NOT signed by {parent.subject}"
            )

    # Verify root is self-signed
    root_pubkey = root_cert.public_key()
    try:
        root_pubkey.verify(
            root_cert.signature,
            root_cert.tbs_certificate_bytes,
            ec.ECDSA(root_cert.signature_hash_algorithm),
        )
    except InvalidSignature:
        raise ValueError("Root certificate is not self-signed")

    return leaf_cert


def _verify_cose_signature(
    leaf_cert: x509.Certificate,
    protected: bytes,
    payload: bytes,
    signature: bytes,
) -> None:
    """Verify the COSE_Sign1 ECDSA-P384 signature using the leaf certificate.

    The COSE signature for ES384 is 96 bytes: r (48 bytes) || s (48 bytes).
    The cryptography library expects DER-encoded (r, s), so we convert.
    """
    sig_structure = _build_sig_structure(protected, payload)

    # COSE ES384 signature is r || s, each 48 bytes (P-384)
    if len(signature) != 96:
        raise ValueError(f"Expected 96-byte ES384 signature, got {len(signature)}")
    r = int.from_bytes(signature[:48], "big")
    s = int.from_bytes(signature[48:], "big")
    der_sig = utils.encode_dss_signature(r, s)

    pubkey = leaf_cert.public_key()
    if not isinstance(pubkey, ec.EllipticCurvePublicKey):
        raise ValueError(f"Leaf certificate has non-EC public key: {type(pubkey)}")

    try:
        pubkey.verify(der_sig, sig_structure, ec.ECDSA(SHA384()))
    except InvalidSignature:
        raise ValueError(
            "COSE_Sign1 signature verification FAILED. "
            "The attestation document was NOT signed by the leaf certificate."
        )


def verify(server_url: str, expected_pcr0: str | None = None) -> None:
    """Full attestation verification flow."""
    # Step 1: Generate random nonce
    nonce_bytes = os.urandom(32)
    nonce_hex = nonce_bytes.hex()
    print(f"[1/6] Generated nonce: {nonce_hex}")

    # Step 2: Fetch attestation
    print(f"[2/6] Requesting attestation from {server_url} ...")
    data = _fetch_attestation(server_url, nonce_hex)
    print(f"       Module: {data['module_id']}")
    print(f"       Timestamp: {data['timestamp']} ({datetime.fromtimestamp(data['timestamp'] / 1000, tz=timezone.utc).isoformat()})")

    # Step 3: Decode COSE_Sign1
    raw_doc = base64.b64decode(data["document"])
    protected, payload_bytes, signature = _decode_cose_sign1(raw_doc)
    payload = _parse_payload(payload_bytes)
    print(f"[3/6] Decoded COSE_Sign1 ({len(raw_doc)} bytes, {len(signature)}-byte signature)")

    # Step 4: Verify certificate chain
    print("[4/6] Verifying certificate chain against AWS Nitro root CA ...")
    leaf_cert = _verify_cert_chain(
        leaf_der=bytes(payload["certificate"]),
        cabundle_der=[bytes(c) for c in payload["cabundle"]],
    )
    print(f"       Leaf cert subject: {leaf_cert.subject}")
    print(f"       Root CA fingerprint: OK (matches AWS Nitro Enclaves Root-G1)")

    # Step 5: Verify COSE_Sign1 signature
    print("[5/6] Verifying ECDSA-P384 signature ...")
    _verify_cose_signature(leaf_cert, protected, payload_bytes, signature)
    print("       Signature: VALID")

    # Step 6: Check nonce and extract results
    print("[6/6] Checking nonce and extracting identity ...")

    doc_nonce = payload.get("nonce")
    if doc_nonce is not None:
        doc_nonce = bytes(doc_nonce)
    if doc_nonce != nonce_bytes:
        print(f"FAIL: Nonce mismatch!")
        print(f"  Sent:     {nonce_hex}")
        print(f"  Received: {doc_nonce.hex() if doc_nonce else 'None'}")
        sys.exit(1)
    print(f"       Nonce: matches (fresh attestation confirmed)")

    # Extract PCRs
    pcrs = payload["pcrs"]
    pcr0 = bytes(pcrs[0]).hex()
    print(f"\n{'='*60}")
    print(f"  ATTESTATION VERIFIED SUCCESSFULLY")
    print(f"{'='*60}")
    print(f"  PCR-0 (enclave image): {pcr0}")
    if 1 in pcrs:
        print(f"  PCR-1 (kernel):        {bytes(pcrs[1]).hex()}")
    if 2 in pcrs:
        print(f"  PCR-2 (application):   {bytes(pcrs[2]).hex()}")

    # Extract server address from user_data
    user_data = payload.get("user_data")
    if user_data is not None:
        addr_bytes = bytes(user_data)
        if len(addr_bytes) == 20:
            server_addr = "0x" + addr_bytes.hex()
            print(f"  Server address:        {server_addr}")
        else:
            print(f"  User data ({len(addr_bytes)} bytes): {addr_bytes.hex()}")

    print(f"  Server address (API):  {data.get('server_address', 'N/A')}")
    print(f"{'='*60}")

    # Optional: compare PCR-0 against expected value
    if expected_pcr0 is not None:
        expected_clean = expected_pcr0.lower().replace(":", "").strip()
        if pcr0 == expected_clean:
            print(f"\n  PCR-0 matches expected value.")
        else:
            print(f"\n  FAIL: PCR-0 does NOT match expected value!")
            print(f"    Got:      {pcr0}")
            print(f"    Expected: {expected_clean}")
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Verify a Monteclaude server attestation document.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python verify_attestation.py https://monteclaude.ai\n"
            "  python verify_attestation.py http://localhost:8001\n"
            "  python verify_attestation.py https://monteclaude.ai --expected-pcr0 aabb...\n"
        ),
    )
    parser.add_argument("server_url", help="Base URL of the Game API")
    parser.add_argument(
        "--expected-pcr0",
        help="Expected PCR-0 hex value to compare against",
        default=None,
    )
    args = parser.parse_args()

    try:
        verify(args.server_url, expected_pcr0=args.expected_pcr0)
    except ValueError as exc:
        print(f"\nVERIFICATION FAILED: {exc}")
        sys.exit(1)
    except requests.RequestException as exc:
        print(f"\nCONNECTION ERROR: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
