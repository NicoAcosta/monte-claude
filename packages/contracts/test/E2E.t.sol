// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Escrow} from "../src/Escrow.sol";
import {EscrowFactory} from "../src/EscrowFactory.sol";
import {ISignatureTransfer} from "../src/interfaces/ISignatureTransfer.sol";
import {MonteClaudio} from "../src/MonteClaudio.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {BaseEscrowTest} from "./BaseEscrowTest.sol";

/// @title E2E tests on Base fork with real USDC
/// @dev Run with: forge test --fork-url <base_rpc> -vvv --match-contract E2E
contract E2ETest is BaseEscrowTest {
    // Base USDC
    address constant USDC = 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913;
    // A USDC whale on Base (Circle's address has lots of USDC)
    address constant USDC_WHALE = 0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA;

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
    uint256 player1Pk;
    address player2;
    uint256 player2Pk;

    uint256 constant BUY_IN = 100e6; // 100 USDC (6 decimals)
    uint16 constant RAKE_BPS = 250;  // 2.5%

    function setUp() public {
        (admin, adminPk) = makeAddrAndKey("admin");
        (alice, alicePk) = makeAddrAndKey("alice");
        (bob, bobPk) = makeAddrAndKey("bob");

        // Assign sorted player aliases
        if (uint160(alice) < uint160(bob)) {
            player1 = alice; player1Pk = alicePk;
            player2 = bob;   player2Pk = bobPk;
        } else {
            player1 = bob;   player1Pk = bobPk;
            player2 = alice; player2Pk = alicePk;
        }

        impl = new Escrow();
        factory = new EscrowFactory(address(impl));

        // Fund players from whale
        vm.startPrank(USDC_WHALE);
        IERC20(USDC).transfer(alice, BUY_IN);
        IERC20(USDC).transfer(bob, BUY_IN);
        vm.stopPrank();
    }

    function _makeConfig() internal view returns (Escrow.Config memory) {
        return Escrow.Config({
            token: USDC,
            admin: admin,
            rakeBeneficiary: rakeBeneficiary,
            depositAmount: BUY_IN,
            rakeBps: RAKE_BPS,
            fundingDeadline: block.timestamp + 300,
            settlementDeadline: block.timestamp + 7200,
            participants: _sorted2(alice, bob)
        });
    }

    // ══════════════════════════════════════════════════════════════════════
    // Happy path: full lifecycle
    // ══════════════════════════════════════════════════════════════════════

    function test_e2e_fullLifecycle() public {
        Escrow.Config memory cfg = _makeConfig();

        // player1 creates escrow and deposits
        vm.prank(player1);
        IERC20(USDC).approve(address(factory), BUY_IN);
        vm.prank(player1);
        address escrowAddr = factory.createAndDeposit(cfg, bytes32(uint256(1)));
        Escrow escrow = Escrow(escrowAddr);

        assertEq(uint256(escrow.status()), uint256(Escrow.Status.FUNDING));
        assertTrue(escrow.hasDeposited(player1));
        assertEq(IERC20(USDC).balanceOf(escrowAddr), BUY_IN);

        // player2 deposits
        vm.prank(player2);
        IERC20(USDC).approve(escrowAddr, BUY_IN);
        vm.prank(player2);
        escrow.deposit(player2);

        assertEq(uint256(escrow.status()), uint256(Escrow.Status.ACTIVE));
        assertTrue(escrow.allDeposited());
        assertEq(IERC20(USDC).balanceOf(escrowAddr), BUY_IN * 2);

        // Settle: player1 wins 150 USDC, player2 gets 50 USDC (from 200 total)
        uint256 balance = IERC20(USDC).balanceOf(escrowAddr);
        Escrow.Payout[] memory payouts = new Escrow.Payout[](2);
        payouts[0] = Escrow.Payout(player1, 150e6);
        payouts[1] = Escrow.Payout(player2, 50e6);

        bytes memory sig = _signSettlement(escrow, payouts, adminPk);
        escrow.settle(payouts, sig);

        assertEq(uint256(escrow.status()), uint256(Escrow.Status.SETTLED));

        // Verify balances
        // player1: 150 USDC - 2.5% rake = 146.25 USDC
        uint256 p1Rake = (150e6 * uint256(RAKE_BPS)) / 10_000;
        uint256 p2Rake = (50e6 * uint256(RAKE_BPS)) / 10_000;
        assertEq(IERC20(USDC).balanceOf(player1), 150e6 - p1Rake);
        assertEq(IERC20(USDC).balanceOf(player2), 50e6 - p2Rake);
        assertEq(IERC20(USDC).balanceOf(rakeBeneficiary), p1Rake + p2Rake);

        // Escrow should be empty
        assertEq(IERC20(USDC).balanceOf(escrowAddr), 0);
    }

    // ══════════════════════════════════════════════════════════════════════
    // Funding timeout -> expire -> withdraw
    // ══════════════════════════════════════════════════════════════════════

    function test_e2e_fundingTimeout() public {
        Escrow.Config memory cfg = _makeConfig();

        // player1 creates escrow and deposits
        vm.prank(player1);
        IERC20(USDC).approve(address(factory), BUY_IN);
        vm.prank(player1);
        address escrowAddr = factory.createAndDeposit(cfg, bytes32(uint256(2)));
        Escrow escrow = Escrow(escrowAddr);

        // player2 never deposits -- funding deadline passes
        vm.warp(cfg.fundingDeadline + 1);
        escrow.expire();

        assertEq(uint256(escrow.status()), uint256(Escrow.Status.EXPIRED));

        // player1 withdraws deposit (no rake)
        uint256 p1Before = IERC20(USDC).balanceOf(player1);
        vm.prank(player1);
        escrow.withdraw();
        uint256 p1After = IERC20(USDC).balanceOf(player1);

        assertEq(p1After - p1Before, BUY_IN);
        assertEq(IERC20(USDC).balanceOf(rakeBeneficiary), 0);
    }

    // ══════════════════════════════════════════════════════════════════════
    // Settlement timeout -> expire -> withdraw
    // ══════════════════════════════════════════════════════════════════════

    function test_e2e_settlementTimeout() public {
        Escrow.Config memory cfg = _makeConfig();

        // Both deposit
        vm.prank(player1);
        IERC20(USDC).approve(address(factory), BUY_IN);
        vm.prank(player1);
        address escrowAddr = factory.createAndDeposit(cfg, bytes32(uint256(3)));
        Escrow escrow = Escrow(escrowAddr);

        vm.prank(player2);
        IERC20(USDC).approve(escrowAddr, BUY_IN);
        vm.prank(player2);
        escrow.deposit(player2);

        assertEq(uint256(escrow.status()), uint256(Escrow.Status.ACTIVE));

        // Settlement deadline passes without settlement
        vm.warp(cfg.settlementDeadline + 1);
        escrow.expire();

        assertEq(uint256(escrow.status()), uint256(Escrow.Status.EXPIRED));

        // Both withdraw
        vm.prank(player1);
        escrow.withdraw();
        vm.prank(player2);
        escrow.withdraw();

        assertEq(IERC20(USDC).balanceOf(player1), BUY_IN);
        assertEq(IERC20(USDC).balanceOf(player2), BUY_IN);
        assertEq(IERC20(USDC).balanceOf(rakeBeneficiary), 0);
        assertEq(IERC20(USDC).balanceOf(escrowAddr), 0);
    }

    // ══════════════════════════════════════════════════════════════════════
    // Deterministic address prediction
    // ══════════════════════════════════════════════════════════════════════

    function test_e2e_deterministicAddress() public {
        Escrow.Config memory cfg = _makeConfig();
        bytes32 salt = bytes32(uint256(4));

        address predicted = factory.getEscrowAddress(cfg, salt);

        vm.prank(player1);
        IERC20(USDC).approve(address(factory), BUY_IN);
        vm.prank(player1);
        address actual = factory.createAndDeposit(cfg, salt);

        assertEq(predicted, actual);
    }
}

/// @title E2E Permit2 tests on Base fork with MONTE token
/// @dev MONTE has native Permit2 support (max allowance for canonical Permit2).
///      These tests deploy MONTE on the fork and use the real Permit2 contract.
///      Run with: forge test --fork-url <base_rpc> -vvv --match-contract E2EPermit2
contract E2EPermit2Test is BaseEscrowTest {
    MonteClaudio monte;
    Escrow impl;
    EscrowFactory factory;

    address admin;
    uint256 adminPk;
    address rakeBeneficiary = makeAddr("rake");
    address alice;
    uint256 alicePk;
    address bob;
    uint256 bobPk;

    // Sorted aliases
    address player1;
    uint256 player1Pk;
    address player2;
    uint256 player2Pk;

    uint256 constant BUY_IN = 1000e18; // 1000 MONTE
    uint16 constant RAKE_BPS = 250;

    function setUp() public {
        (admin, adminPk) = makeAddrAndKey("admin");
        (alice, alicePk) = makeAddrAndKey("alice");
        (bob, bobPk) = makeAddrAndKey("bob");

        if (uint160(alice) < uint160(bob)) {
            player1 = alice; player1Pk = alicePk;
            player2 = bob;   player2Pk = bobPk;
        } else {
            player1 = bob;   player1Pk = bobPk;
            player2 = alice; player2Pk = alicePk;
        }

        // On a fork, makeAddrAndKey addresses may collide with deployed contracts.
        // Clear any code so Permit2 uses ECDSA (not EIP-1271) for signature verification.
        vm.etch(alice, "");
        vm.etch(bob, "");

        // Deploy MONTE on the fork — it's ownerless, anyone can claim the faucet
        monte = new MonteClaudio();

        impl = new Escrow();
        factory = new EscrowFactory(address(impl));

        // Players claim from faucet (10,000 MONTE each)
        vm.prank(alice);
        monte.faucet();
        vm.prank(bob);
        monte.faucet();
    }

    function _makeConfig() internal view returns (Escrow.Config memory) {
        return Escrow.Config({
            token: address(monte),
            admin: admin,
            rakeBeneficiary: rakeBeneficiary,
            depositAmount: BUY_IN,
            rakeBps: RAKE_BPS,
            fundingDeadline: block.timestamp + 300,
            settlementDeadline: block.timestamp + 7200,
            participants: _sorted2(alice, bob)
        });
    }

    // ══════════════════════════════════════════════════════════════════════
    // MONTE has native Permit2: no approval tx needed
    // ══════════════════════════════════════════════════════════════════════

    function test_e2e_permit2_monteNativeAllowance() public view {
        // MONTE returns max allowance for Permit2 — verify on fork
        uint256 allowance = monte.allowance(alice, PERMIT2_ADDRESS);
        assertEq(allowance, type(uint256).max);
    }

    // ══════════════════════════════════════════════════════════════════════
    // Full lifecycle via Permit2: create + deposit + settle
    // ══════════════════════════════════════════════════════════════════════

    function test_e2e_permit2_fullLifecycle() public {
        Escrow.Config memory cfg = _makeConfig();

        // player1 creates escrow via Permit2 (no ERC-20 approve needed for MONTE)
        ISignatureTransfer.PermitTransferFrom memory permit1 = ISignatureTransfer.PermitTransferFrom({
            permitted: ISignatureTransfer.TokenPermissions({ token: address(monte), amount: BUY_IN }),
            nonce: 0,
            deadline: block.timestamp + 100
        });
        bytes memory sig1 = _signPermit2Transfer(permit1, player1Pk, address(factory));

        vm.prank(player1);
        address escrowAddr = factory.createAndDepositWithPermit2(cfg, bytes32(uint256(1)), permit1, sig1);
        Escrow escrow = Escrow(escrowAddr);

        assertEq(uint256(escrow.status()), uint256(Escrow.Status.FUNDING));
        assertTrue(escrow.hasDeposited(player1));
        assertEq(monte.balanceOf(escrowAddr), BUY_IN);

        // player2 deposits via Permit2
        ISignatureTransfer.PermitTransferFrom memory permit2 = ISignatureTransfer.PermitTransferFrom({
            permitted: ISignatureTransfer.TokenPermissions({ token: address(monte), amount: BUY_IN }),
            nonce: 0,
            deadline: block.timestamp + 100
        });
        bytes memory sig2 = _signPermit2Transfer(permit2, player2Pk, escrowAddr);

        vm.prank(player2);
        escrow.depositWithPermit2(player2, permit2, player2, sig2);

        assertEq(uint256(escrow.status()), uint256(Escrow.Status.ACTIVE));
        assertTrue(escrow.allDeposited());
        assertEq(monte.balanceOf(escrowAddr), BUY_IN * 2);

        // Settle: player1 wins 1500, player2 gets 500 (from 2000 total)
        Escrow.Payout[] memory payouts = new Escrow.Payout[](2);
        payouts[0] = Escrow.Payout(player1, 1500e18);
        payouts[1] = Escrow.Payout(player2, 500e18);

        bytes memory settleSig = _signSettlement(escrow, payouts, adminPk);
        escrow.settle(payouts, settleSig);

        assertEq(uint256(escrow.status()), uint256(Escrow.Status.SETTLED));

        // Verify balances after rake
        uint256 p1Rake = (1500e18 * uint256(RAKE_BPS)) / 10_000;
        uint256 p2Rake = (500e18 * uint256(RAKE_BPS)) / 10_000;
        assertEq(monte.balanceOf(player1), 10_000e18 - BUY_IN + 1500e18 - p1Rake);
        assertEq(monte.balanceOf(player2), 10_000e18 - BUY_IN + 500e18 - p2Rake);
        assertEq(monte.balanceOf(rakeBeneficiary), p1Rake + p2Rake);
        assertEq(monte.balanceOf(escrowAddr), 0);
    }

    // ══════════════════════════════════════════════════════════════════════
    // Mixed flow: Permit2 create + standard deposit
    // ══════════════════════════════════════════════════════════════════════

    function test_e2e_permit2_mixedFlow() public {
        Escrow.Config memory cfg = _makeConfig();

        // player1 creates via Permit2
        ISignatureTransfer.PermitTransferFrom memory permit1 = ISignatureTransfer.PermitTransferFrom({
            permitted: ISignatureTransfer.TokenPermissions({ token: address(monte), amount: BUY_IN }),
            nonce: 0,
            deadline: block.timestamp + 100
        });
        bytes memory sig1 = _signPermit2Transfer(permit1, player1Pk, address(factory));

        vm.prank(player1);
        address escrowAddr = factory.createAndDepositWithPermit2(cfg, bytes32(uint256(2)), permit1, sig1);
        Escrow escrow = Escrow(escrowAddr);

        // player2 deposits via standard approve
        vm.prank(player2);
        monte.approve(escrowAddr, BUY_IN);
        vm.prank(player2);
        escrow.deposit(player2);

        assertEq(uint256(escrow.status()), uint256(Escrow.Status.ACTIVE));
        assertTrue(escrow.allDeposited());
    }

    // ══════════════════════════════════════════════════════════════════════
    // Permit2 deposit on existing escrow (standard create, Permit2 deposit)
    // ══════════════════════════════════════════════════════════════════════

    function test_e2e_permit2_depositOnly() public {
        Escrow.Config memory cfg = _makeConfig();

        // player1 creates via standard approve
        vm.prank(player1);
        monte.approve(address(factory), BUY_IN);
        vm.prank(player1);
        address escrowAddr = factory.createAndDeposit(cfg, bytes32(uint256(3)));
        Escrow escrow = Escrow(escrowAddr);

        // player2 deposits via Permit2
        ISignatureTransfer.PermitTransferFrom memory permit2 = ISignatureTransfer.PermitTransferFrom({
            permitted: ISignatureTransfer.TokenPermissions({ token: address(monte), amount: BUY_IN }),
            nonce: 0,
            deadline: block.timestamp + 100
        });
        bytes memory sig2 = _signPermit2Transfer(permit2, player2Pk, escrowAddr);

        vm.prank(player2);
        escrow.depositWithPermit2(player2, permit2, player2, sig2);

        assertEq(uint256(escrow.status()), uint256(Escrow.Status.ACTIVE));
        assertTrue(escrow.allDeposited());
        assertEq(monte.balanceOf(escrowAddr), BUY_IN * 2);
    }

    // ══════════════════════════════════════════════════════════════════════
    // Funding timeout with Permit2 deposit → expire → withdraw
    // ══════════════════════════════════════════════════════════════════════

    function test_e2e_permit2_fundingTimeout() public {
        Escrow.Config memory cfg = _makeConfig();

        // player1 creates via Permit2
        ISignatureTransfer.PermitTransferFrom memory permit1 = ISignatureTransfer.PermitTransferFrom({
            permitted: ISignatureTransfer.TokenPermissions({ token: address(monte), amount: BUY_IN }),
            nonce: 0,
            deadline: block.timestamp + 100
        });
        bytes memory sig1 = _signPermit2Transfer(permit1, player1Pk, address(factory));

        vm.prank(player1);
        address escrowAddr = factory.createAndDepositWithPermit2(cfg, bytes32(uint256(4)), permit1, sig1);
        Escrow escrow = Escrow(escrowAddr);

        uint256 p1BalBefore = monte.balanceOf(player1);

        // player2 never deposits — funding deadline passes
        vm.warp(cfg.fundingDeadline + 1);
        escrow.expire();

        assertEq(uint256(escrow.status()), uint256(Escrow.Status.EXPIRED));

        // player1 withdraws (no rake)
        vm.prank(player1);
        escrow.withdraw();

        assertEq(monte.balanceOf(player1), p1BalBefore + BUY_IN);
        assertEq(monte.balanceOf(rakeBeneficiary), 0);
    }
}
