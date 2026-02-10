"""Tests for escrow_service PCR-0 integration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from web3 import Web3

from core.attestation import AttestationPayload, AttestationResult, NsmError
from core.escrow_service import check_funding, get_escrow_info, get_settlement
from core.game_config import GameConfig


# ── Test constants ────────────────────────────────────────

FAKE_PCR0 = bytes(range(48))
FAKE_PCR0_HASH = Web3.keccak(FAKE_PCR0)

ADMIN_PK = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"


def _mock_env(extra: dict | None = None) -> dict:
    env = {
        "server_private_key": ADMIN_PK,
        "base_rpc_url": "http://localhost:8545",
        "rake_bps": 250,
        "rake_beneficiary": "0x90F79bf6EB2c4f870365E785982E1f101E93b906",
        "factory_address": "0x1111111111111111111111111111111111111111",
        "funding_timeout": 300,
        "settlement_timeout": 7200,
        "chain_id": 8453,
    }
    if extra:
        env.update(extra)
    return env


def _mock_game(wallet_a: str, wallet_b: str, *, game_over: bool = False, chips_a: int = 1000, chips_b: int = 1000):
    player_a = MagicMock()
    player_a.wallet_address = wallet_a
    player_a.name = "alice"
    player_a.chips = chips_a

    player_b = MagicMock()
    player_b.wallet_address = wallet_b
    player_b.name = "bob"
    player_b.chips = chips_b

    game = MagicMock()
    game.players = [player_a, player_b]
    game.player_count = 2
    game.game_over = game_over
    game.starting_chips = 1000
    return game


def _mock_attestation_result() -> AttestationResult:
    payload = AttestationPayload(
        module_id="test-module",
        timestamp=1000,
        digest="SHA384",
        pcrs={0: FAKE_PCR0, 1: b"\x00" * 48, 2: b"\x00" * 48},
        certificate=b"cert",
        cabundle=[b"ca"],
    )
    return AttestationResult(raw_document=b"raw", payload=payload)


WALLET_A = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
WALLET_B = "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC"


# ══════════════════════════════════════════════════════════
# get_escrow_info — PCR-0 binding
# ══════════════════════════════════════════════════════════

class TestGetEscrowInfoPcr0:
    @patch("core.escrow_service.compute_escrow_address", return_value="0xaabbccdd" + "00" * 16)
    @patch("core.escrow_service.get_env_config")
    @patch("core.escrow_service.get_server_address", return_value="0x" + "aa" * 20)
    @patch("core.escrow_service.get_attestation")
    def test_fetches_pcr0_from_nsm(self, mock_attest, mock_addr, mock_env_cfg, mock_compute):
        mock_env_cfg.return_value = _mock_env()
        mock_attest.return_value = _mock_attestation_result()

        game = _mock_game(WALLET_A, WALLET_B)
        config = GameConfig(mode="onchain", buy_in=100, max_players=2, token="0x" + "ff" * 20)

        result = get_escrow_info(game, config)

        mock_attest.assert_called_once()
        assert config.escrow_config is not None
        assert config.escrow_config.pcr0_hash == FAKE_PCR0_HASH

    @patch("core.escrow_service.compute_escrow_address", return_value="0xaabbccdd" + "00" * 16)
    @patch("core.escrow_service.get_env_config")
    @patch("core.escrow_service.get_server_address", return_value="0x" + "aa" * 20)
    @patch("core.escrow_service.get_attestation")
    def test_zero_pcr0_when_no_nsm(self, mock_attest, mock_addr, mock_env_cfg, mock_compute):
        mock_env_cfg.return_value = _mock_env()
        mock_attest.side_effect = NsmError("NSM device not found")

        game = _mock_game(WALLET_A, WALLET_B)
        config = GameConfig(mode="onchain", buy_in=100, max_players=2, token="0x" + "ff" * 20)

        result = get_escrow_info(game, config)

        assert config.escrow_config is not None
        assert config.escrow_config.pcr0_hash == b"\x00" * 32

    @patch("core.escrow_service.compute_escrow_address", return_value="0xaabbccdd" + "00" * 16)
    @patch("core.escrow_service.get_env_config")
    @patch("core.escrow_service.get_server_address", return_value="0x" + "aa" * 20)
    @patch("core.escrow_service.get_attestation")
    def test_admin_signature_present(self, mock_attest, mock_addr, mock_env_cfg, mock_compute):
        mock_env_cfg.return_value = _mock_env()
        mock_attest.side_effect = NsmError("NSM device not found")

        game = _mock_game(WALLET_A, WALLET_B)
        config = GameConfig(mode="onchain", buy_in=100, max_players=2, token="0x" + "ff" * 20)

        result = get_escrow_info(game, config)

        assert "admin_signature" in result
        sig_bytes = bytes.fromhex(result["admin_signature"].removeprefix("0x"))
        assert len(sig_bytes) == 65
        assert config.admin_signature == result["admin_signature"]


# ══════════════════════════════════════════════════════════
# get_settlement — PCR-0 binding
# ══════════════════════════════════════════════════════════

class TestGetSettlementPcr0:
    @patch("core.escrow_service.sign_settlement", return_value="0x" + "ab" * 65)
    @patch("core.escrow_service.get_env_config")
    @patch("core.escrow_service.get_attestation")
    def test_includes_pcr0_in_settlement(self, mock_attest, mock_env_cfg, mock_sign):
        mock_env_cfg.return_value = _mock_env()
        mock_attest.return_value = _mock_attestation_result()

        game = _mock_game(WALLET_A, WALLET_B, game_over=True, chips_a=2000, chips_b=0)
        config = GameConfig(mode="onchain", buy_in=100, max_players=2, token="0x" + "ff" * 20)
        config.escrow_address = "0x" + "ee" * 20
        config.pcr0_hash = FAKE_PCR0_HASH

        result = get_settlement(game, config)

        assert "pcr0" in result
        assert result["pcr0"] == FAKE_PCR0
        # sign_settlement should have been called with pcr0 kwarg
        _, kwargs = mock_sign.call_args
        assert kwargs.get("pcr0") == FAKE_PCR0

    @patch("core.escrow_service.sign_settlement", return_value="0x" + "ab" * 65)
    @patch("core.escrow_service.get_env_config")
    def test_empty_pcr0_when_hash_zero(self, mock_env_cfg, mock_sign):
        mock_env_cfg.return_value = _mock_env()

        game = _mock_game(WALLET_A, WALLET_B, game_over=True, chips_a=2000, chips_b=0)
        config = GameConfig(mode="onchain", buy_in=100, max_players=2, token="0x" + "ff" * 20)
        config.escrow_address = "0x" + "ee" * 20
        config.pcr0_hash = b"\x00" * 32

        result = get_settlement(game, config)

        assert result["pcr0"] == b""
        _, kwargs = mock_sign.call_args
        assert kwargs.get("pcr0") == b""

    @patch("core.escrow_service.sign_settlement", return_value="0x" + "ab" * 65)
    @patch("core.escrow_service.get_env_config")
    @patch("core.escrow_service.get_attestation")
    def test_fails_when_nsm_was_available_but_now_gone(self, mock_attest, mock_env_cfg, mock_sign):
        mock_env_cfg.return_value = _mock_env()
        mock_attest.side_effect = NsmError("NSM device not found")

        game = _mock_game(WALLET_A, WALLET_B, game_over=True, chips_a=2000, chips_b=0)
        config = GameConfig(mode="onchain", buy_in=100, max_players=2, token="0x" + "ff" * 20)
        config.escrow_address = "0x" + "ee" * 20
        config.pcr0_hash = FAKE_PCR0_HASH  # Non-zero — NSM was available at creation

        with pytest.raises(RuntimeError, match="Attestation required"):
            get_settlement(game, config)


# ══════════════════════════════════════════════════════════
# get_escrow_info — guide field
# ══════════════════════════════════════════════════════════

class TestEscrowGuide:
    @patch("core.escrow_service.compute_escrow_address", return_value="0xaabbccdd" + "00" * 16)
    @patch("core.escrow_service.get_env_config")
    @patch("core.escrow_service.get_server_address", return_value="0x" + "aa" * 20)
    @patch("core.escrow_service.get_attestation")
    def test_guide_present_in_result(self, mock_attest, mock_addr, mock_env_cfg, mock_compute):
        mock_env_cfg.return_value = _mock_env()
        mock_attest.side_effect = NsmError("NSM device not found")

        game = _mock_game(WALLET_A, WALLET_B)
        config = GameConfig(mode="onchain", buy_in=100, max_players=2, token="0x" + "ff" * 20)

        result = get_escrow_info(game, config, game_id="test-123")

        assert "guide" in result
        guide = result["guide"]
        # Guide steps are now structured: list of {to, data, description}
        assert len(guide["first_depositor"]) > 0
        assert len(guide["subsequent_depositor"]) > 0
        for step in guide["first_depositor"]:
            assert "to" in step and "data" in step and "description" in step
        assert guide["verification"]
        assert len(guide["notes"]) > 0

    @patch("core.escrow_service.compute_escrow_address", return_value="0xaabbccdd" + "00" * 16)
    @patch("core.escrow_service.get_env_config")
    @patch("core.escrow_service.get_server_address", return_value="0x" + "aa" * 20)
    @patch("core.escrow_service.get_attestation")
    def test_guide_contains_concrete_addresses(self, mock_attest, mock_addr, mock_env_cfg, mock_compute):
        mock_env_cfg.return_value = _mock_env()
        mock_attest.side_effect = NsmError("NSM device not found")

        game = _mock_game(WALLET_A, WALLET_B)
        token = "0x" + "ff" * 20
        config = GameConfig(mode="onchain", buy_in=100, max_players=2, token=token)

        result = get_escrow_info(game, config, game_id="test-456")

        guide = result["guide"]
        factory = _mock_env()["factory_address"]
        # First depositor steps reference factory (as `to` target)
        first_tos = [s["to"].lower() for s in guide["first_depositor"]]
        assert factory.lower() in first_tos
        assert token.lower() in first_tos
        # Subsequent depositor steps reference escrow address
        sub_tos = [s["to"].lower() for s in guide["subsequent_depositor"]]
        assert result["escrow_address"].lower() in sub_tos

    @patch("core.escrow_service.compute_escrow_address", return_value="0xaabbccdd" + "00" * 16)
    @patch("core.escrow_service.get_env_config")
    @patch("core.escrow_service.get_server_address", return_value="0x" + "aa" * 20)
    @patch("core.escrow_service.get_attestation")
    def test_guide_verification_includes_game_id(self, mock_attest, mock_addr, mock_env_cfg, mock_compute):
        mock_env_cfg.return_value = _mock_env()
        mock_attest.side_effect = NsmError("NSM device not found")

        game = _mock_game(WALLET_A, WALLET_B)
        config = GameConfig(mode="onchain", buy_in=100, max_players=2, token="0x" + "ff" * 20)

        result = get_escrow_info(game, config, game_id="my-game-id")

        assert "my-game-id" in result["guide"]["verification"]

    @patch("core.escrow_service.compute_escrow_address", return_value="0xaabbccdd" + "00" * 16)
    @patch("core.escrow_service.get_env_config")
    @patch("core.escrow_service.get_server_address", return_value="0x" + "aa" * 20)
    @patch("core.escrow_service.get_attestation")
    def test_approve_calldata_in_result(self, mock_attest, mock_addr, mock_env_cfg, mock_compute):
        """Result should include pre-built ERC20 approve calldata."""
        mock_env_cfg.return_value = _mock_env()
        mock_attest.side_effect = NsmError("NSM device not found")

        game = _mock_game(WALLET_A, WALLET_B)
        config = GameConfig(mode="onchain", buy_in=100, max_players=2, token="0x" + "ff" * 20)

        result = get_escrow_info(game, config, game_id="test-approve")

        assert "calldata_approve_factory" in result
        assert "calldata_approve_escrow" in result
        # Both should be hex-encoded calldata starting with 0x
        assert result["calldata_approve_factory"].startswith("0x")
        assert result["calldata_approve_escrow"].startswith("0x")
        # approve(address,uint256) selector = 0x095ea7b3
        assert result["calldata_approve_factory"].startswith("0x095ea7b3")
        assert result["calldata_approve_escrow"].startswith("0x095ea7b3")


# ══════════════════════════════════════════════════════════
# check_funding — Web3 error handling
# ══════════════════════════════════════════════════════════

class TestCheckFundingErrors:
    @patch("core.escrow_service.check_deposit_status")
    @patch("core.escrow_service.get_env_config")
    def test_web3_error_raises_value_error(self, mock_env_cfg, mock_check):
        """When check_deposit_status raises (e.g. escrow not deployed), we get ValueError."""
        mock_env_cfg.return_value = _mock_env()
        mock_check.side_effect = Exception("execution reverted")

        game = _mock_game(WALLET_A, WALLET_B)
        config = GameConfig(mode="onchain", buy_in=100, max_players=2, token="0x" + "ff" * 20)
        config.escrow_address = "0x" + "ee" * 20

        with pytest.raises(ValueError, match="may not be deployed yet"):
            check_funding(game, config)

    @patch("core.escrow_service.check_deposit_status")
    @patch("core.escrow_service.get_env_config")
    def test_error_message_mentions_factory(self, mock_env_cfg, mock_check):
        """Error message should tell the user to use createAndDeposit on the factory."""
        mock_env_cfg.return_value = _mock_env()
        mock_check.side_effect = Exception("could not decode")

        game = _mock_game(WALLET_A, WALLET_B)
        config = GameConfig(mode="onchain", buy_in=100, max_players=2, token="0x" + "ff" * 20)
        config.escrow_address = "0x" + "ee" * 20

        with pytest.raises(ValueError, match="createAndDeposit"):
            check_funding(game, config)

    @patch("core.escrow_service.check_deposit_status")
    @patch("core.escrow_service.get_env_config")
    def test_successful_funding_check(self, mock_env_cfg, mock_check):
        """Normal case — no exception, returns deposit statuses."""
        mock_env_cfg.return_value = _mock_env()
        mock_check.return_value = [(WALLET_A, True), (WALLET_B, False)]

        game = _mock_game(WALLET_A, WALLET_B)
        config = GameConfig(mode="onchain", buy_in=100, max_players=2, token="0x" + "ff" * 20)
        config.escrow_address = "0x" + "ee" * 20

        result = check_funding(game, config)
        assert result["all_deposited"] is False
        assert len(result["statuses"]) == 2
