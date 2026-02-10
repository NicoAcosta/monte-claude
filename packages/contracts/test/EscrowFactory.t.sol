// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Escrow} from "../src/Escrow.sol";
import {EscrowFactory} from "../src/EscrowFactory.sol";
import {ISignatureTransfer} from "../src/interfaces/ISignatureTransfer.sol";
import {BaseEscrowTest, MockERC20} from "./BaseEscrowTest.sol";

contract EscrowFactoryTest is BaseEscrowTest {
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

    function setUp() public {
        (admin, adminPk) = makeAddrAndKey("admin");
        (alice, alicePk) = makeAddrAndKey("alice");
        (bob, bobPk) = makeAddrAndKey("bob");

        token = new MockERC20();
        impl = new Escrow();
        factory = new EscrowFactory(address(impl));
        _deployPermit2();
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
            participants: _sorted2(alice, bob),
            pcr0Hash: bytes32(0)
        });
    }

    function test_createAndDeposit() public {
        Escrow.Config memory cfg = _defaultConfig();
        bytes32 salt = bytes32(uint256(1));
        bytes memory adminSig = _signCreateEscrow(address(factory), cfg, salt, adminPk);

        vm.prank(player1);
        token.approve(address(factory), DEPOSIT);
        vm.prank(player1);
        address escrow = factory.createAndDeposit(cfg, salt, adminSig);

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
        bytes memory adminSig = _signCreateEscrow(address(factory), cfg, salt, adminPk);

        vm.prank(player1);
        token.approve(address(factory), DEPOSIT);
        vm.prank(player1);
        address actual = factory.createAndDeposit(cfg, salt, adminSig);

        assertEq(predicted, actual);
    }

    function test_createAndDeposit_duplicateReverts() public {
        Escrow.Config memory cfg = _defaultConfig();
        bytes32 salt = bytes32(uint256(1));
        bytes memory adminSig = _signCreateEscrow(address(factory), cfg, salt, adminPk);

        vm.prank(player1);
        token.approve(address(factory), DEPOSIT);
        vm.prank(player1);
        factory.createAndDeposit(cfg, salt, adminSig);

        // Same config + salt should revert (CREATE2 collision)
        vm.prank(player1);
        token.approve(address(factory), DEPOSIT);
        vm.prank(player1);
        vm.expectRevert();
        factory.createAndDeposit(cfg, salt, adminSig);
    }

    function test_createAndDeposit_differentSalts() public {
        Escrow.Config memory cfg = _defaultConfig();

        bytes32 salt1 = bytes32(uint256(1));
        bytes memory adminSig1 = _signCreateEscrow(address(factory), cfg, salt1, adminPk);
        vm.prank(player1);
        token.approve(address(factory), DEPOSIT);
        vm.prank(player1);
        address escrow1 = factory.createAndDeposit(cfg, salt1, adminSig1);

        bytes32 salt2 = bytes32(uint256(2));
        bytes memory adminSig2 = _signCreateEscrow(address(factory), cfg, salt2, adminPk);
        vm.prank(player1);
        token.approve(address(factory), DEPOSIT);
        vm.prank(player1);
        address escrow2 = factory.createAndDeposit(cfg, salt2, adminSig2);

        assertTrue(escrow1 != escrow2);
    }

    function test_implementation() public view {
        assertEq(factory.IMPLEMENTATION(), address(impl));
    }

    function test_createAndDeposit_callerMustBeParticipant() public {
        Escrow.Config memory cfg = _defaultConfig();
        bytes32 salt = bytes32(uint256(1));
        bytes memory adminSig = _signCreateEscrow(address(factory), cfg, salt, adminPk);

        // Charlie is not a participant but tries to create
        address charlie = makeAddr("charlie");
        token.mint(charlie, DEPOSIT * 10);
        vm.prank(charlie);
        token.approve(address(factory), DEPOSIT);
        vm.prank(charlie);
        // recordDeposit will revert because charlie is not a participant
        vm.expectRevert(abi.encodeWithSelector(Escrow.NotParticipant.selector, charlie));
        factory.createAndDeposit(cfg, salt, adminSig);
    }

    // ══════════════════════════════════════════════════════════════════════
    // ADMIN SIGNATURE VERIFICATION TESTS
    // ══════════════════════════════════════════════════════════════════════

    function test_createAndDeposit_validAdminSig() public {
        Escrow.Config memory cfg = _defaultConfig();
        bytes32 salt = bytes32(uint256(100));
        bytes memory adminSig = _signCreateEscrow(address(factory), cfg, salt, adminPk);

        vm.prank(player1);
        token.approve(address(factory), DEPOSIT);
        vm.prank(player1);
        address escrow = factory.createAndDeposit(cfg, salt, adminSig);

        assertTrue(Escrow(escrow).initialized());
    }

    function test_createAndDeposit_invalidAdminSig() public {
        Escrow.Config memory cfg = _defaultConfig();
        bytes32 salt = bytes32(uint256(101));

        // Sign with random key (not admin)
        (, uint256 randomPk) = makeAddrAndKey("random");
        bytes memory badSig = _signCreateEscrow(address(factory), cfg, salt, randomPk);

        vm.prank(player1);
        token.approve(address(factory), DEPOSIT);
        vm.prank(player1);
        vm.expectRevert(EscrowFactory.InvalidAdminSignature.selector);
        factory.createAndDeposit(cfg, salt, badSig);
    }

    function test_createAndDeposit_wrongSalt() public {
        Escrow.Config memory cfg = _defaultConfig();
        bytes32 saltA = bytes32(uint256(200));
        bytes32 saltB = bytes32(uint256(201));

        // Admin signs with saltA, caller uses saltB
        bytes memory adminSig = _signCreateEscrow(address(factory), cfg, saltA, adminPk);

        vm.prank(player1);
        token.approve(address(factory), DEPOSIT);
        vm.prank(player1);
        vm.expectRevert(EscrowFactory.InvalidAdminSignature.selector);
        factory.createAndDeposit(cfg, saltB, adminSig);
    }

    function test_createAndDeposit_wrongConfig() public {
        Escrow.Config memory cfgA = _defaultConfig();
        bytes32 salt = bytes32(uint256(300));

        // Admin signs configA
        bytes memory adminSig = _signCreateEscrow(address(factory), cfgA, salt, adminPk);

        // Caller modifies deposit amount
        Escrow.Config memory cfgB = _defaultConfig();
        cfgB.depositAmount = DEPOSIT * 2;
        token.mint(player1, DEPOSIT * 10);

        vm.prank(player1);
        token.approve(address(factory), cfgB.depositAmount);
        vm.prank(player1);
        vm.expectRevert(EscrowFactory.InvalidAdminSignature.selector);
        factory.createAndDeposit(cfgB, salt, adminSig);
    }

    function test_createAndDepositWithPermit2_validAdminSig() public {
        Escrow.Config memory cfg = _defaultConfig();
        bytes32 salt = bytes32(uint256(400));
        bytes memory adminSig = _signCreateEscrow(address(factory), cfg, salt, adminPk);

        vm.prank(player1);
        token.approve(PERMIT2_ADDRESS, type(uint256).max);

        uint256 pk = player1 == alice ? alicePk : bobPk;
        ISignatureTransfer.PermitTransferFrom memory permit = ISignatureTransfer.PermitTransferFrom({
            permitted: ISignatureTransfer.TokenPermissions({token: address(token), amount: DEPOSIT}),
            nonce: 0,
            deadline: block.timestamp + 100
        });
        bytes memory sig = _signPermit2Transfer(permit, pk, address(factory));

        vm.prank(player1);
        address escrow = factory.createAndDepositWithPermit2(cfg, salt, adminSig, permit, sig);

        assertTrue(Escrow(escrow).initialized());
        assertTrue(Escrow(escrow).hasDeposited(player1));
    }

    function test_createAndDepositWithPermit2_invalidAdminSig() public {
        Escrow.Config memory cfg = _defaultConfig();
        bytes32 salt = bytes32(uint256(401));

        (, uint256 randomPk) = makeAddrAndKey("random2");
        bytes memory badSig = _signCreateEscrow(address(factory), cfg, salt, randomPk);

        vm.prank(player1);
        token.approve(PERMIT2_ADDRESS, type(uint256).max);

        uint256 pk = player1 == alice ? alicePk : bobPk;
        ISignatureTransfer.PermitTransferFrom memory permit = ISignatureTransfer.PermitTransferFrom({
            permitted: ISignatureTransfer.TokenPermissions({token: address(token), amount: DEPOSIT}),
            nonce: 0,
            deadline: block.timestamp + 100
        });
        bytes memory sig = _signPermit2Transfer(permit, pk, address(factory));

        vm.prank(player1);
        vm.expectRevert(EscrowFactory.InvalidAdminSignature.selector);
        factory.createAndDepositWithPermit2(cfg, salt, badSig, permit, sig);
    }

    function test_getEscrowAddress_unchanged() public view {
        // getEscrowAddress is a pure view function — no signature needed
        Escrow.Config memory cfg = _defaultConfig();
        bytes32 salt = bytes32(uint256(500));

        address addr = factory.getEscrowAddress(cfg, salt);
        assertTrue(addr != address(0));
    }

    function test_createAndDeposit_addressMatchesWithSig() public {
        Escrow.Config memory cfg = _defaultConfig();
        bytes32 salt = bytes32(uint256(600));

        // Predicted address (no sig needed for view)
        address predicted = factory.getEscrowAddress(cfg, salt);

        // Actual deployment (with sig)
        bytes memory adminSig = _signCreateEscrow(address(factory), cfg, salt, adminPk);
        vm.prank(player1);
        token.approve(address(factory), DEPOSIT);
        vm.prank(player1);
        address actual = factory.createAndDeposit(cfg, salt, adminSig);

        assertEq(predicted, actual);
    }

    // ══════════════════════════════════════════════════════════════════════
    // PERMIT2 FACTORY TESTS
    // ══════════════════════════════════════════════════════════════════════

    function test_createAndDepositWithPermit2() public {
        Escrow.Config memory cfg = _defaultConfig();
        bytes32 salt = bytes32(uint256(1));
        bytes memory adminSig = _signCreateEscrow(address(factory), cfg, salt, adminPk);

        // player1 approves Permit2 and signs transfer
        vm.prank(player1);
        token.approve(PERMIT2_ADDRESS, type(uint256).max);

        uint256 pk = player1 == alice ? alicePk : bobPk;
        ISignatureTransfer.PermitTransferFrom memory permit = ISignatureTransfer.PermitTransferFrom({
            permitted: ISignatureTransfer.TokenPermissions({token: address(token), amount: DEPOSIT}),
            nonce: 0,
            deadline: block.timestamp + 100
        });

        // Need to predict the escrow address since Permit2 sig includes spender (= factory)
        bytes memory sig = _signPermit2Transfer(permit, pk, address(factory));

        vm.prank(player1);
        address escrow = factory.createAndDepositWithPermit2(cfg, salt, adminSig, permit, sig);

        Escrow e = Escrow(escrow);
        assertTrue(e.initialized());
        assertEq(e.token(), address(token));
        assertEq(e.admin(), admin);
        assertEq(e.depositAmount(), DEPOSIT);
        assertTrue(e.hasDeposited(player1));
        assertEq(e.depositCount(), 1);
        assertEq(token.balanceOf(escrow), DEPOSIT);
    }

    function test_createAndDepositWithPermit2_addressMatch() public {
        Escrow.Config memory cfg = _defaultConfig();
        bytes32 salt = bytes32(uint256(1));

        address predicted = factory.getEscrowAddress(cfg, salt);
        bytes memory adminSig = _signCreateEscrow(address(factory), cfg, salt, adminPk);

        vm.prank(player1);
        token.approve(PERMIT2_ADDRESS, type(uint256).max);

        uint256 pk = player1 == alice ? alicePk : bobPk;
        ISignatureTransfer.PermitTransferFrom memory permit = ISignatureTransfer.PermitTransferFrom({
            permitted: ISignatureTransfer.TokenPermissions({token: address(token), amount: DEPOSIT}),
            nonce: 0,
            deadline: block.timestamp + 100
        });
        bytes memory sig = _signPermit2Transfer(permit, pk, address(factory));

        vm.prank(player1);
        address actual = factory.createAndDepositWithPermit2(cfg, salt, adminSig, permit, sig);

        assertEq(predicted, actual);
    }

    function test_createAndDepositWithPermit2_mixedFlow() public {
        Escrow.Config memory cfg = _defaultConfig();
        bytes32 salt = bytes32(uint256(1));
        bytes memory adminSig = _signCreateEscrow(address(factory), cfg, salt, adminPk);

        // player1 creates via Permit2
        vm.prank(player1);
        token.approve(PERMIT2_ADDRESS, type(uint256).max);

        uint256 pk = player1 == alice ? alicePk : bobPk;
        ISignatureTransfer.PermitTransferFrom memory permit = ISignatureTransfer.PermitTransferFrom({
            permitted: ISignatureTransfer.TokenPermissions({token: address(token), amount: DEPOSIT}),
            nonce: 0,
            deadline: block.timestamp + 100
        });
        bytes memory sig = _signPermit2Transfer(permit, pk, address(factory));

        vm.prank(player1);
        address addr = factory.createAndDepositWithPermit2(cfg, salt, adminSig, permit, sig);
        Escrow escrow = Escrow(addr);

        assertEq(uint256(escrow.status()), uint256(Escrow.Status.FUNDING));

        // player2 deposits via standard approve → should transition to ACTIVE
        vm.prank(player2);
        token.approve(addr, DEPOSIT);
        vm.prank(player2);
        escrow.deposit(player2);

        assertEq(uint256(escrow.status()), uint256(Escrow.Status.ACTIVE));
        assertTrue(escrow.allDeposited());
    }

    // ══════════════════════════════════════════════════════════════════════
    // FUZZ TESTS
    // ══════════════════════════════════════════════════════════════════════

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
            participants: _sorted2(alice, bob),
            pcr0Hash: bytes32(0)
        });

        bytes32 salt = bytes32(depositAmt);
        bytes memory adminSig = _signCreateEscrow(address(factory), cfg, salt, adminPk);

        vm.prank(player1);
        token.approve(address(factory), depositAmt);
        vm.prank(player1);
        address escrow = factory.createAndDeposit(cfg, salt, adminSig);

        assertEq(token.balanceOf(escrow), depositAmt);
        assertEq(Escrow(escrow).depositAmount(), depositAmt);
    }
}
