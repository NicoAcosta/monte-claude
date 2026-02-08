// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Escrow} from "../src/Escrow.sol";
import {EscrowFactory} from "../src/EscrowFactory.sol";
import {BaseEscrowTest, MockERC20} from "./BaseEscrowTest.sol";

contract EscrowFactoryTest is BaseEscrowTest {
    MockERC20 token;
    Escrow impl;
    EscrowFactory factory;

    address admin = makeAddr("admin");
    address rakeBeneficiary = makeAddr("rake");
    address alice = makeAddr("alice");
    address bob = makeAddr("bob");

    // Sorted aliases (assigned in setUp)
    address player1;
    address player2;

    uint256 constant DEPOSIT = 100e6;

    function setUp() public {
        token = new MockERC20();
        impl = new Escrow();
        factory = new EscrowFactory(address(impl));
        token.mint(alice, DEPOSIT * 10);
        token.mint(bob, DEPOSIT * 10);
        vm.warp(100);

        // Assign sorted player aliases
        if (uint160(alice) < uint160(bob)) {
            player1 = alice;
            player2 = bob;
        } else {
            player1 = bob;
            player2 = alice;
        }
    }

    function _defaultConfig() internal view returns (Escrow.Config memory) {
        return Escrow.Config({
            token: address(token),
            admin: admin,
            rakeBeneficiary: rakeBeneficiary,
            depositAmount: DEPOSIT,
            rakeBps: 250,
            fundingDeadline: 1000,
            settlementDeadline: 2000,
            participants: _sorted2(alice, bob)
        });
    }

    function test_createAndDeposit() public {
        Escrow.Config memory cfg = _defaultConfig();

        vm.prank(player1);
        token.approve(address(factory), DEPOSIT);
        vm.prank(player1);
        address escrow = factory.createAndDeposit(cfg, bytes32(uint256(1)));

        // Escrow should be initialized
        Escrow e = Escrow(escrow);
        assertTrue(e.initialized());
        assertEq(e.token(), address(token));
        assertEq(e.admin(), admin);
        assertEq(e.depositAmount(), DEPOSIT);

        // player1's deposit should be recorded
        assertTrue(e.hasDeposited(player1));
        assertEq(e.depositCount(), 1);
        assertEq(token.balanceOf(escrow), DEPOSIT);
    }

    function test_getEscrowAddress_deterministic() public view {
        Escrow.Config memory cfg = _defaultConfig();
        bytes32 salt = bytes32(uint256(1));

        address predicted = factory.getEscrowAddress(cfg, salt);
        // Calling again should return the same address
        assertEq(predicted, factory.getEscrowAddress(cfg, salt));
    }

    function test_getEscrowAddress_matchesActual() public {
        Escrow.Config memory cfg = _defaultConfig();
        bytes32 salt = bytes32(uint256(1));

        address predicted = factory.getEscrowAddress(cfg, salt);

        vm.prank(player1);
        token.approve(address(factory), DEPOSIT);
        vm.prank(player1);
        address actual = factory.createAndDeposit(cfg, salt);

        assertEq(predicted, actual);
    }

    function test_createAndDeposit_duplicateReverts() public {
        Escrow.Config memory cfg = _defaultConfig();
        bytes32 salt = bytes32(uint256(1));

        vm.prank(player1);
        token.approve(address(factory), DEPOSIT);
        vm.prank(player1);
        factory.createAndDeposit(cfg, salt);

        // Same config + salt should revert (CREATE2 collision)
        vm.prank(player1);
        token.approve(address(factory), DEPOSIT);
        vm.prank(player1);
        vm.expectRevert();
        factory.createAndDeposit(cfg, salt);
    }

    function test_createAndDeposit_differentSalts() public {
        Escrow.Config memory cfg = _defaultConfig();

        vm.prank(player1);
        token.approve(address(factory), DEPOSIT);
        vm.prank(player1);
        address escrow1 = factory.createAndDeposit(cfg, bytes32(uint256(1)));

        vm.prank(player1);
        token.approve(address(factory), DEPOSIT);
        vm.prank(player1);
        address escrow2 = factory.createAndDeposit(cfg, bytes32(uint256(2)));

        assertTrue(escrow1 != escrow2);
    }

    function test_implementation() public view {
        assertEq(factory.IMPLEMENTATION(), address(impl));
    }

    function test_createAndDeposit_callerMustBeParticipant() public {
        Escrow.Config memory cfg = _defaultConfig();

        // Charlie is not a participant but tries to create
        address charlie = makeAddr("charlie");
        token.mint(charlie, DEPOSIT * 10);
        vm.prank(charlie);
        token.approve(address(factory), DEPOSIT);
        vm.prank(charlie);
        // recordDeposit will revert because charlie is not a participant
        vm.expectRevert(abi.encodeWithSelector(Escrow.NotParticipant.selector, charlie));
        factory.createAndDeposit(cfg, bytes32(uint256(1)));
    }

    function testFuzz_differentConfigs(uint256 depositAmt) public {
        depositAmt = bound(depositAmt, 1, 1e30);
        token.mint(player1, depositAmt);

        Escrow.Config memory cfg = Escrow.Config({
            token: address(token),
            admin: admin,
            rakeBeneficiary: rakeBeneficiary,
            depositAmount: depositAmt,
            rakeBps: 250,
            fundingDeadline: 1000,
            settlementDeadline: 2000,
            participants: _sorted2(alice, bob)
        });

        vm.prank(player1);
        token.approve(address(factory), depositAmt);
        vm.prank(player1);
        address escrow = factory.createAndDeposit(cfg, bytes32(depositAmt));

        assertEq(token.balanceOf(escrow), depositAmt);
        assertEq(Escrow(escrow).depositAmount(), depositAmt);
    }
}
