"""NSM attestation: ioctl to /dev/nsm, COSE_Sign1 parsing.

Pure functions + frozen dataclasses. No global state.
"""

from __future__ import annotations

import ctypes
import fcntl
import struct
from dataclasses import dataclass
from typing import Any

import cbor2


# ── Exceptions ────────────────────────────────────────────


class NsmError(Exception):
    """Raised when NSM device interaction fails."""


# ── Data types ────────────────────────────────────────────


@dataclass(frozen=True)
class AttestationPayload:
    """Parsed fields from a COSE_Sign1 attestation document."""

    module_id: str
    timestamp: int
    digest: str
    pcrs: dict[int, bytes]
    certificate: bytes
    cabundle: list[bytes]
    user_data: bytes | None = None
    nonce: bytes | None = None
    public_key: bytes | None = None


@dataclass(frozen=True)
class AttestationResult:
    """Raw COSE_Sign1 document + parsed payload."""

    raw_document: bytes
    payload: AttestationPayload


# ── NSM ioctl ─────────────────────────────────────────────

_NSM_IOCTL_REQUEST = 0  # ioctl number for NSM requests
_NSM_DEVICE = "/dev/nsm"
_MAX_RESPONSE_SIZE = 0x4000  # 16 KiB


class _IoVec(ctypes.Structure):
    _fields_ = [
        ("iov_base", ctypes.c_void_p),
        ("iov_len", ctypes.c_size_t),
    ]


def nsm_get_attestation(
    user_data: bytes | None = None,
    nonce: bytes | None = None,
    public_key: bytes | None = None,
) -> bytes:
    """Low-level NSM ioctl. Returns raw COSE_Sign1 bytes.

    Raises NsmError if /dev/nsm is unavailable or returns an error.
    """
    request_payload: dict[str, Any] = {}
    if user_data is not None:
        request_payload["user_data"] = user_data
    if nonce is not None:
        request_payload["nonce"] = nonce
    if public_key is not None:
        request_payload["public_key"] = public_key

    request_cbor = cbor2.dumps({"GetAttestation": request_payload})

    try:
        fd = open(_NSM_DEVICE, "r+b", buffering=0)
    except FileNotFoundError:
        raise NsmError("NSM device not found")
    except PermissionError:
        raise NsmError("NSM device permission denied")

    try:
        # Build request iovec
        req_buf = ctypes.create_string_buffer(request_cbor)
        req_iov = _IoVec(
            ctypes.cast(req_buf, ctypes.c_void_p),
            len(request_cbor),
        )

        # Build response iovec
        resp_buf = ctypes.create_string_buffer(_MAX_RESPONSE_SIZE)
        resp_iov = _IoVec(
            ctypes.cast(resp_buf, ctypes.c_void_p),
            _MAX_RESPONSE_SIZE,
        )

        # Pack iovecs into the message struct expected by NSM:
        # struct { struct iovec request; struct iovec response; }
        msg = bytes(req_iov) + bytes(resp_iov)
        msg_buf = ctypes.create_string_buffer(msg, len(msg))

        try:
            fcntl.ioctl(fd.fileno(), _NSM_IOCTL_REQUEST, msg_buf)
        except OSError as exc:
            raise NsmError(f"NSM ioctl failed: {exc}")

        # Read back the response iovec to get the actual length
        iov_size = ctypes.sizeof(_IoVec)
        resp_iov_bytes = msg_buf.raw[iov_size : iov_size * 2]
        # iov_len is the second field (size_t)
        ptr_size = ctypes.sizeof(ctypes.c_void_p)
        resp_len = struct.unpack_from("N", resp_iov_bytes, ptr_size)[0]

        resp_cbor = resp_buf.raw[:resp_len]
    finally:
        fd.close()

    # Decode CBOR response
    try:
        response = cbor2.loads(resp_cbor)
    except Exception as exc:
        raise NsmError(f"Failed to decode NSM response: {exc}")

    # Extract the attestation document
    if not isinstance(response, dict) or "GetAttestation" not in response:
        raise NsmError(f"Unexpected NSM response structure: {response!r}")

    inner = response["GetAttestation"]
    if isinstance(inner, dict) and "document" in inner:
        return bytes(inner["document"])

    raise NsmError(f"NSM error: {inner!r}")


# ── COSE_Sign1 parsing ───────────────────────────────────


def parse_attestation_doc(raw: bytes) -> AttestationPayload:
    """Parse a COSE_Sign1 attestation document into an AttestationPayload.

    The raw bytes must be CBOR-encoded COSE_Sign1: Tag(18, [protected, unprotected, payload, signature]).
    The payload is itself CBOR-encoded with NSM attestation fields.

    Raises ValueError on malformed input or missing required fields.
    """
    try:
        decoded = cbor2.loads(raw)
    except Exception as exc:
        raise ValueError(f"malformed CBOR: {exc}")

    # Must be a CBOR tag 18 (COSE_Sign1)
    if not isinstance(decoded, cbor2.CBORTag) or decoded.tag != 18:
        raise ValueError("Not a COSE_Sign1 document (expected CBOR tag 18)")

    array = decoded.value
    if not isinstance(array, (list, tuple)) or len(array) != 4:
        raise ValueError("malformed COSE_Sign1: expected 4-element array")

    payload_bytes = array[2]
    if isinstance(payload_bytes, memoryview):
        payload_bytes = bytes(payload_bytes)

    try:
        payload = cbor2.loads(payload_bytes)
    except Exception as exc:
        raise ValueError(f"malformed COSE_Sign1 payload: {exc}")

    if not isinstance(payload, dict):
        raise ValueError("malformed COSE_Sign1 payload: expected map")

    # Validate required fields
    required = ("module_id", "timestamp", "digest", "pcrs", "certificate", "cabundle")
    for field in required:
        if field not in payload:
            raise ValueError(f"Missing required field: {field}")

    # Normalize PCR map: keys may be ints, values are bytes
    raw_pcrs = payload["pcrs"]
    pcrs: dict[int, bytes] = {}
    for k, v in raw_pcrs.items():
        pcrs[int(k)] = bytes(v) if not isinstance(v, bytes) else v

    return AttestationPayload(
        module_id=payload["module_id"],
        timestamp=payload["timestamp"],
        digest=payload["digest"],
        pcrs=pcrs,
        certificate=bytes(payload["certificate"]) if not isinstance(payload["certificate"], bytes) else payload["certificate"],
        cabundle=[bytes(c) if not isinstance(c, bytes) else c for c in payload["cabundle"]],
        user_data=bytes(payload["user_data"]) if payload.get("user_data") is not None else None,
        nonce=bytes(payload["nonce"]) if payload.get("nonce") is not None else None,
        public_key=bytes(payload["public_key"]) if payload.get("public_key") is not None else None,
    )


# ── Combined ──────────────────────────────────────────────


def get_attestation(
    user_data: bytes | None = None,
    nonce: bytes | None = None,
    public_key: bytes | None = None,
) -> AttestationResult:
    """Get attestation from NSM and parse it.

    Raises NsmError on device failures, ValueError on parse failures.
    """
    raw_doc = nsm_get_attestation(
        user_data=user_data,
        nonce=nonce,
        public_key=public_key,
    )
    payload = parse_attestation_doc(raw_doc)
    return AttestationResult(raw_document=raw_doc, payload=payload)
