"""Tests for NSM attestation: parse_attestation_doc + GET /attestation endpoint."""

from __future__ import annotations

import base64
from unittest.mock import patch

import cbor2
import pytest
from fastapi.testclient import TestClient


# ── Helpers ───────────────────────────────────────────────


def _make_attestation_payload(
    *,
    module_id: str = "test-enclave",
    timestamp: int = 1700000000000,
    digest: str = "SHA384",
    pcrs: dict[int, bytes] | None = None,
    certificate: bytes = b"fake-cert",
    cabundle: list[bytes] | None = None,
    user_data: bytes | None = None,
    nonce: bytes | None = None,
    public_key: bytes | None = None,
) -> dict:
    """Build a payload dict matching NSM attestation document structure."""
    if pcrs is None:
        pcrs = {
            0: b"\xaa" * 48,
            1: b"\xbb" * 48,
            2: b"\xcc" * 48,
        }
    payload: dict = {
        "module_id": module_id,
        "timestamp": timestamp,
        "digest": digest,
        "pcrs": pcrs,
        "certificate": certificate,
        "cabundle": cabundle or [b"fake-ca"],
    }
    if user_data is not None:
        payload["user_data"] = user_data
    if nonce is not None:
        payload["nonce"] = nonce
    if public_key is not None:
        payload["public_key"] = public_key
    return payload


def _make_fake_cose_sign1(payload_dict: dict) -> bytes:
    """Build a synthetic COSE_Sign1 structure (CBOR tag 18).

    Real COSE_Sign1: Tag(18, [protected, unprotected, payload, signature])
    We use empty protected/unprotected and fake signature.
    """
    protected = b""
    unprotected = {}
    payload_bytes = cbor2.dumps(payload_dict)
    signature = b"\x00" * 64
    return cbor2.dumps(
        cbor2.CBORTag(18, [protected, unprotected, payload_bytes, signature])
    )


# ── parse_attestation_doc unit tests ─────────────────────


class TestParseAttestationDoc:
    def test_parses_minimal_doc(self):
        from core.attestation import parse_attestation_doc

        payload = _make_attestation_payload()
        raw = _make_fake_cose_sign1(payload)

        result = parse_attestation_doc(raw)

        assert result.module_id == "test-enclave"
        assert result.timestamp == 1700000000000
        assert result.digest == "SHA384"
        assert result.pcrs[0] == b"\xaa" * 48
        assert result.pcrs[1] == b"\xbb" * 48
        assert result.pcrs[2] == b"\xcc" * 48
        assert result.user_data is None
        assert result.nonce is None

    def test_includes_user_data_and_nonce(self):
        from core.attestation import parse_attestation_doc

        user_data = b"\xde\xad\xbe\xef"
        nonce = b"\xca\xfe" * 10
        payload = _make_attestation_payload(user_data=user_data, nonce=nonce)
        raw = _make_fake_cose_sign1(payload)

        result = parse_attestation_doc(raw)

        assert result.user_data == user_data
        assert result.nonce == nonce

    def test_pcr_values_are_bytes(self):
        from core.attestation import parse_attestation_doc

        payload = _make_attestation_payload()
        raw = _make_fake_cose_sign1(payload)

        result = parse_attestation_doc(raw)

        for pcr_val in result.pcrs.values():
            assert isinstance(pcr_val, bytes)
            assert len(pcr_val) == 48  # SHA-384

    def test_raises_on_malformed_cbor(self):
        from core.attestation import parse_attestation_doc

        # Truly invalid CBOR (truncated)
        with pytest.raises(ValueError, match="malformed"):
            parse_attestation_doc(b"\xd8\x12\x84")  # tag 18, array(4), then truncated

    def test_raises_on_missing_required_fields(self):
        from core.attestation import parse_attestation_doc

        # Payload missing module_id
        incomplete = {"timestamp": 123, "digest": "SHA384", "pcrs": {}, "certificate": b"x", "cabundle": []}
        raw = _make_fake_cose_sign1(incomplete)

        with pytest.raises(ValueError, match="module_id"):
            parse_attestation_doc(raw)

    def test_raises_on_non_cose_sign1(self):
        from core.attestation import parse_attestation_doc

        # Valid CBOR but not a COSE_Sign1 tag
        raw = cbor2.dumps({"not": "cose"})

        with pytest.raises(ValueError, match="COSE_Sign1"):
            parse_attestation_doc(raw)

    def test_preserves_all_pcrs_in_map(self):
        from core.attestation import parse_attestation_doc

        pcrs = {i: bytes([i]) * 48 for i in range(5)}
        payload = _make_attestation_payload(pcrs=pcrs)
        raw = _make_fake_cose_sign1(payload)

        result = parse_attestation_doc(raw)

        assert len(result.pcrs) == 5
        for i in range(5):
            assert result.pcrs[i] == bytes([i]) * 48

    def test_includes_certificate_and_cabundle(self):
        from core.attestation import parse_attestation_doc

        payload = _make_attestation_payload(
            certificate=b"test-cert-data",
            cabundle=[b"ca-1", b"ca-2"],
        )
        raw = _make_fake_cose_sign1(payload)

        result = parse_attestation_doc(raw)

        assert result.certificate == b"test-cert-data"
        assert result.cabundle == [b"ca-1", b"ca-2"]


# ── GET /attestation endpoint tests ──────────────────────


def _make_mock_attestation_result():
    """Build a mock AttestationResult for endpoint tests."""
    from core.attestation import AttestationPayload, AttestationResult

    payload = AttestationPayload(
        module_id="test-enclave",
        timestamp=1700000000000,
        digest="SHA384",
        pcrs={
            0: b"\xaa" * 48,
            1: b"\xbb" * 48,
            2: b"\xcc" * 48,
            3: b"\xdd" * 48,
        },
        certificate=b"fake-cert",
        cabundle=[b"fake-ca"],
        user_data=bytes.fromhex("d8dA6BF26964aF9D7eEd9e03E53415D37aA96045".lower()),
        nonce=None,
        public_key=None,
    )
    raw_doc = _make_fake_cose_sign1(_make_attestation_payload(
        user_data=payload.user_data,
    ))
    return AttestationResult(raw_document=raw_doc, payload=payload)


_TEST_PRIVATE_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
_TEST_ADDRESS = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"


class TestAttestationEndpoint:
    def _get_client(self):
        from game_api.app import app
        return TestClient(app, raise_server_exceptions=False)

    @patch.dict("os.environ", {"SERVER_PRIVATE_KEY": _TEST_PRIVATE_KEY})
    @patch("core.attestation.get_attestation")
    def test_happy_path(self, mock_get):
        mock_get.return_value = _make_mock_attestation_result()
        client = self._get_client()

        resp = client.get("/attestation")

        assert resp.status_code == 200
        body = resp.json()
        assert body["module_id"] == "test-enclave"
        assert body["timestamp"] == 1700000000000
        assert body["digest"] == "SHA384"
        assert body["server_address"] == _TEST_ADDRESS
        assert "0" in body["pcrs"]
        assert "1" in body["pcrs"]
        assert "2" in body["pcrs"]
        # Only PCR 0-2 in parsed response
        assert "3" not in body["pcrs"]

    @patch.dict("os.environ", {"SERVER_PRIVATE_KEY": _TEST_PRIVATE_KEY})
    @patch("core.attestation.get_attestation")
    def test_document_is_valid_base64(self, mock_get):
        result = _make_mock_attestation_result()
        mock_get.return_value = result
        client = self._get_client()

        resp = client.get("/attestation")
        body = resp.json()

        raw = base64.b64decode(body["document"])
        assert raw == result.raw_document

    @patch.dict("os.environ", {"SERVER_PRIVATE_KEY": _TEST_PRIVATE_KEY})
    @patch("core.attestation.get_attestation")
    def test_nonce_forwarded_to_nsm(self, mock_get):
        mock_get.return_value = _make_mock_attestation_result()
        client = self._get_client()

        resp = client.get("/attestation?nonce=deadbeef")

        assert resp.status_code == 200
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["nonce"] == bytes.fromhex("deadbeef")

    @patch.dict("os.environ", {"SERVER_PRIVATE_KEY": _TEST_PRIVATE_KEY})
    def test_400_on_non_hex_nonce(self):
        client = self._get_client()

        resp = client.get("/attestation?nonce=not-hex!")

        assert resp.status_code == 400
        assert "hex" in resp.json()["detail"].lower()

    @patch.dict("os.environ", {"SERVER_PRIVATE_KEY": _TEST_PRIVATE_KEY})
    def test_400_on_nonce_too_long(self):
        client = self._get_client()
        # 513 bytes = 1026 hex chars
        long_nonce = "aa" * 513

        resp = client.get(f"/attestation?nonce={long_nonce}")

        assert resp.status_code == 400
        assert "too long" in resp.json()["detail"].lower()

    @patch.dict("os.environ", {"SERVER_PRIVATE_KEY": _TEST_PRIVATE_KEY})
    @patch("core.attestation.get_attestation")
    def test_dev_mode_when_nsm_unavailable(self, mock_get):
        from core.attestation import NsmError
        mock_get.side_effect = NsmError("NSM device not found")
        client = self._get_client()

        resp = client.get("/attestation?nonce=aabb")

        assert resp.status_code == 200
        data = resp.json()
        assert data["module_id"] == "dev-mode"
        assert data["pcrs"]["0"] == "0" * 96  # 48 zero bytes
        assert data["nonce"] == "aabb"
        assert data["server_address"]  # present and non-empty

    @patch.dict("os.environ", {}, clear=False)
    def test_500_when_server_key_not_set(self):
        import os
        # Ensure SERVER_PRIVATE_KEY is unset
        old = os.environ.pop("SERVER_PRIVATE_KEY", None)
        try:
            client = self._get_client()
            resp = client.get("/attestation")
            assert resp.status_code == 500
            assert "identity" in resp.json()["detail"].lower() or "configured" in resp.json()["detail"].lower()
        finally:
            if old is not None:
                os.environ["SERVER_PRIVATE_KEY"] = old

    @patch.dict("os.environ", {"SERVER_PRIVATE_KEY": _TEST_PRIVATE_KEY})
    @patch("core.attestation.get_attestation")
    def test_user_data_contains_server_address(self, mock_get):
        """Verify the endpoint passes server address as user_data to NSM."""
        mock_get.return_value = _make_mock_attestation_result()
        client = self._get_client()

        client.get("/attestation")

        call_kwargs = mock_get.call_args[1]
        # user_data should be 20 bytes (Ethereum address without 0x prefix)
        assert len(call_kwargs["user_data"]) == 20

    @patch.dict("os.environ", {"SERVER_PRIVATE_KEY": _TEST_PRIVATE_KEY})
    @patch("core.attestation.get_attestation")
    def test_nonce_512_bytes_accepted(self, mock_get):
        """Exactly 512 bytes is the limit — should be accepted."""
        mock_get.return_value = _make_mock_attestation_result()
        client = self._get_client()

        resp = client.get(f"/attestation?nonce={'aa' * 512}")

        assert resp.status_code == 200
