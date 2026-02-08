// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {Escrow} from "../src/Escrow.sol";
import {EscrowFactory} from "../src/EscrowFactory.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";

/// @title E2E tests on Base fork with real USDC
/// @dev Run with: forge test --fork-url <base_rpc> -vvv --match-contract E2E
contract E2ETest is Test {
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
    address bob;

    // Sorted aliases (assigned in setUp)
    address player1;
    address player2;

    uint256 constant BUY_IN = 100e6; // 100 USDC (6 decimals)
    uint16 constant RAKE_BPS = 250;  // 2.5%

    /// @dev Sort addresses ascending (contract requires sorted participants)
    function _sorted2(address a, address b) internal pure returns (address[] memory) {
        address[] memory arr = new address[](2);
        if (uint160(a) < uint160(b)) {
            arr[0] = a; arr[1] = b;
        } else {
            arr[0] = b; arr[1] = a;
        }
        return arr;
    }

    function setUp() public {
        (admin, adminPk) = makeAddrAndKey("admin");
        alice = makeAddr("alice");
        bob = makeAddr("bob");

        // Assign sorted player aliases
        if (uint160(alice) < uint160(bob)) {
            player1 = alice;
            player2 = bob;
        } else {
            player1 = bob;
            player2 = alice;
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

    function _signSettlement(Escrow escrow, Escrow.Payout[] memory payouts)
        internal
        view
        returns (bytes memory)
    {
        bytes32 domainSeparator = keccak256(
            abi.encode(
                keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                keccak256("TimeBasedEscrow"),
                keccak256("1"),
                block.chainid,
                address(escrow)
            )
        );

        bytes32[] memory payoutHashes = new bytes32[](payouts.length);
        for (uint256 i = 0; i < payouts.length; i++) {
            payoutHashes[i] = keccak256(
                abi.encode(
                    keccak256("Payout(address recipient,uint256 amount)"),
                    payouts[i].recipient,
                    payouts[i].amount
                )
            );
        }
        bytes32 structHash = keccak256(
            abi.encode(
                keccak256("Settle(Payout[] payouts)Payout(address recipient,uint256 amount)"),
                keccak256(abi.encodePacked(payoutHashes))
            )
        );

        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", domainSeparator, structHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(adminPk, digest);
        return abi.encodePacked(r, s, v);
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

        bytes memory sig = _signSettlement(escrow, payouts);
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
