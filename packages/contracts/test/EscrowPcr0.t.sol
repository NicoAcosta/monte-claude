// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Escrow} from "../src/Escrow.sol";
import {EscrowFactory} from "../src/EscrowFactory.sol";
import {BaseEscrowTest, MockERC20} from "./BaseEscrowTest.sol";

contract EscrowPcr0Test is BaseEscrowTest {
    MockERC20 token;
    Escrow impl;
    EscrowFactory factory;

    address admin;
    uint256 adminPk;
    address rakeBeneficiary = makeAddr("rake");
    address alice;
    uint256 alicePk;
    address bob;
    uint256 bobPk;

    // Sorted aliases (assigned in setUp)
    address player1;
    address player2;

    uint256 constant DEPOSIT = 100e6;
    uint16 constant RAKE_BPS = 250;
    uint256 constant FUNDING_DEADLINE = 1000;
    uint256 constant SETTLEMENT_DEADLINE = 2000;

    // Fake PCR-0 values (48 bytes each, as in Nitro Enclave)
    bytes constant PCR0_A = hex"aabbccddaabbccddaabbccddaabbccddaabbccddaabbccddaabbccddaabbccddaabbccddaabbccddaabbccddaabbccdd";
    bytes constant PCR0_B = hex"11223344112233441122334411223344112233441122334411223344112233441122334411223344112233441122334411223344";

    function setUp() public {
        (admin, adminPk) = makeAddrAndKey("admin");
        (alice, alicePk) = makeAddrAndKey("alice");
        (bob, bobPk) = makeAddrAndKey("bob");

        token = new MockERC20();
        impl = new Escrow();
        factory = new EscrowFactory(address(impl));

        if (uint160(alice) < uint160(bob)) {
            player1 = alice;
            player2 = bob;
        } else {
            player1 = bob;
            player2 = alice;
        }

        token.mint(alice, DEPOSIT * 10);
        token.mint(bob, DEPOSIT * 10);

        vm.warp(100);
    }

    // ── Helpers ──────────────────────────────────────────────────────────

    function _configWithPcr0(bytes32 pcr0Hash) internal view returns (Escrow.Config memory) {
        return Escrow.Config({
            token: address(token),
            admin: admin,
            rakeBeneficiary: rakeBeneficiary,
            depositAmount: DEPOSIT,
            rakeBps: RAKE_BPS,
            fundingDeadline: FUNDING_DEADLINE,
            settlementDeadline: SETTLEMENT_DEADLINE,
            participants: _sorted2(alice, bob),
            pcr0Hash: pcr0Hash
        });
    }

    function _deployAndFund(Escrow.Config memory cfg) internal returns (Escrow escrow) {
        bytes memory adminSig = _signCreateEscrow(address(factory), cfg, bytes32(uint256(1)), adminPk);
        vm.prank(player1);
        token.approve(address(factory), DEPOSIT);
        vm.prank(player1);
        address addr = factory.createAndDeposit(cfg, bytes32(uint256(1)), adminSig);
        escrow = Escrow(addr);

        vm.prank(player2);
        token.approve(address(escrow), DEPOSIT);
        vm.prank(player2);
        escrow.deposit(player2);
    }

    // ══════════════════════════════════════════════════════════════════════
    // PCR-0 ENFORCEMENT TESTS
    // ══════════════════════════════════════════════════════════════════════

    function test_settle_with_valid_pcr0() public {
        bytes32 pcr0Hash = keccak256(PCR0_A);
        Escrow escrow = _deployAndFund(_configWithPcr0(pcr0Hash));

        uint256 balance = token.balanceOf(address(escrow));
        Escrow.Payout[] memory payouts = new Escrow.Payout[](2);
        payouts[0] = Escrow.Payout(player1, balance);
        payouts[1] = Escrow.Payout(player2, 0);

        bytes memory sig = _signSettlement(escrow, payouts, PCR0_A, adminPk);
        escrow.settle(payouts, PCR0_A, sig);

        assertEq(uint256(escrow.status()), uint256(Escrow.Status.SETTLED));
    }

    function test_settle_reverts_wrong_pcr0() public {
        bytes32 pcr0Hash = keccak256(PCR0_A);
        Escrow escrow = _deployAndFund(_configWithPcr0(pcr0Hash));

        uint256 balance = token.balanceOf(address(escrow));
        Escrow.Payout[] memory payouts = new Escrow.Payout[](2);
        payouts[0] = Escrow.Payout(player1, balance);
        payouts[1] = Escrow.Payout(player2, 0);

        // Sign with PCR0_B (wrong PCR-0)
        bytes memory sig = _signSettlement(escrow, payouts, PCR0_B, adminPk);
        vm.expectRevert(Escrow.Pcr0Mismatch.selector);
        escrow.settle(payouts, PCR0_B, sig);
    }

    function test_settle_reverts_empty_pcr0_when_required() public {
        bytes32 pcr0Hash = keccak256(PCR0_A);
        Escrow escrow = _deployAndFund(_configWithPcr0(pcr0Hash));

        uint256 balance = token.balanceOf(address(escrow));
        Escrow.Payout[] memory payouts = new Escrow.Payout[](2);
        payouts[0] = Escrow.Payout(player1, balance);
        payouts[1] = Escrow.Payout(player2, 0);

        // Sign with empty pcr0
        bytes memory sig = _signSettlement(escrow, payouts, bytes(""), adminPk);
        vm.expectRevert(Escrow.Pcr0Mismatch.selector);
        escrow.settle(payouts, bytes(""), sig);
    }

    function test_settle_skips_check_when_pcr0hash_zero() public {
        // Dev mode: pcr0Hash = bytes32(0) → no enforcement
        Escrow escrow = _deployAndFund(_configWithPcr0(bytes32(0)));

        uint256 balance = token.balanceOf(address(escrow));
        Escrow.Payout[] memory payouts = new Escrow.Payout[](2);
        payouts[0] = Escrow.Payout(player1, balance);
        payouts[1] = Escrow.Payout(player2, 0);

        // Empty pcr0 works when pcr0Hash is zero
        bytes memory sig = _signSettlement(escrow, payouts, bytes(""), adminPk);
        escrow.settle(payouts, bytes(""), sig);

        assertEq(uint256(escrow.status()), uint256(Escrow.Status.SETTLED));
    }

    function test_settle_with_pcr0_wrong_length() public {
        bytes32 pcr0Hash = keccak256(PCR0_A);
        Escrow escrow = _deployAndFund(_configWithPcr0(pcr0Hash));

        uint256 balance = token.balanceOf(address(escrow));
        Escrow.Payout[] memory payouts = new Escrow.Payout[](2);
        payouts[0] = Escrow.Payout(player1, balance);
        payouts[1] = Escrow.Payout(player2, 0);

        // 32 bytes instead of 48
        bytes memory wrongLen = hex"aabbccddaabbccddaabbccddaabbccddaabbccddaabbccddaabbccddaabbccdd";
        bytes memory sig = _signSettlement(escrow, payouts, wrongLen, adminPk);
        vm.expectRevert(Escrow.Pcr0Mismatch.selector);
        escrow.settle(payouts, wrongLen, sig);
    }

    function test_factory_salt_changes_with_pcr0hash() public {
        bytes32 hash1 = keccak256(PCR0_A);
        bytes32 hash2 = keccak256(PCR0_B);
        bytes32 salt = bytes32(uint256(42));

        Escrow.Config memory cfg1 = _configWithPcr0(hash1);
        Escrow.Config memory cfg2 = _configWithPcr0(hash2);

        address addr1 = factory.getEscrowAddress(cfg1, salt);
        address addr2 = factory.getEscrowAddress(cfg2, salt);

        assertTrue(addr1 != addr2, "Different pcr0Hash should produce different escrow addresses");
    }

    function test_pcr0Hash_stored() public {
        bytes32 pcr0Hash = keccak256(PCR0_A);
        Escrow escrow = _deployAndFund(_configWithPcr0(pcr0Hash));
        assertEq(escrow.pcr0Hash(), pcr0Hash);
    }

    function test_pcr0Hash_zero_stored() public {
        Escrow escrow = _deployAndFund(_configWithPcr0(bytes32(0)));
        assertEq(escrow.pcr0Hash(), bytes32(0));
    }
}
