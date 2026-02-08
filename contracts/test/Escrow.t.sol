// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test, console} from "forge-std/Test.sol";
import {Escrow} from "../src/Escrow.sol";
import {EscrowFactory} from "../src/EscrowFactory.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// @dev Simple ERC20 for testing
contract MockERC20 is ERC20 {
    constructor() ERC20("Mock", "MCK") {}
    function mint(address to, uint256 amount) external { _mint(to, amount); }
}

/// @dev Token that returns false on transfer for blocklisted recipients
contract FalseReturnToken is ERC20 {
    mapping(address => bool) public blocked;
    constructor() ERC20("FalseReturn", "FRT") {}
    function mint(address to, uint256 amount) external { _mint(to, amount); }
    function setBlocked(address addr, bool val) external { blocked[addr] = val; }
    function transfer(address to, uint256 amount) public override returns (bool) {
        if (blocked[to]) return false;
        return super.transfer(to, amount);
    }
}

contract EscrowTest is Test {
    MockERC20 token;
    Escrow impl;
    EscrowFactory factory;

    address admin;
    uint256 adminPk;
    address rakeBeneficiary = makeAddr("rake");
    address alice = makeAddr("alice");
    address bob = makeAddr("bob");
    address charlie = makeAddr("charlie");

    // Sorted aliases (assigned in setUp)
    address player1; // lowest address of alice, bob
    address player2; // highest address of alice, bob
    address player3; // for 3-player: third in sorted order of alice, bob, charlie

    uint256 constant DEPOSIT = 100e6; // 100 USDC-like
    uint16 constant RAKE_BPS = 250;   // 2.5%
    uint256 constant FUNDING_DEADLINE = 1000;
    uint256 constant SETTLEMENT_DEADLINE = 2000;

    function setUp() public {
        (admin, adminPk) = makeAddrAndKey("admin");

        token = new MockERC20();
        impl = new Escrow();
        factory = new EscrowFactory(address(impl));

        // Assign sorted player aliases (2-player)
        if (uint160(alice) < uint160(bob)) {
            player1 = alice;
            player2 = bob;
        } else {
            player1 = bob;
            player2 = alice;
        }

        // Assign sorted player aliases (3-player)
        address[] memory sorted3 = _sorted3(alice, bob, charlie);
        player3 = sorted3[2];
        // player1 and player2 for 3-player case come from sorted3[0] and sorted3[1]
        // but we keep the 2-player player1/player2 for the default 2-player config.
        // For 3-player tests we use _sorted3 directly.

        // Mint tokens to players
        token.mint(alice, DEPOSIT * 10);
        token.mint(bob, DEPOSIT * 10);
        token.mint(charlie, DEPOSIT * 10);

        // Warp to a time before funding deadline
        vm.warp(100);
    }

    // ── Helpers ──────────────────────────────────────────────────────────

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

    function _sorted3(address a, address b, address c) internal pure returns (address[] memory) {
        address[] memory arr = new address[](3);
        arr[0] = a; arr[1] = b; arr[2] = c;
        // Bubble sort 3 elements
        if (uint160(arr[0]) > uint160(arr[1])) (arr[0], arr[1]) = (arr[1], arr[0]);
        if (uint160(arr[1]) > uint160(arr[2])) (arr[1], arr[2]) = (arr[2], arr[1]);
        if (uint160(arr[0]) > uint160(arr[1])) (arr[0], arr[1]) = (arr[1], arr[0]);
        return arr;
    }

    function _defaultConfig() internal view returns (Escrow.Config memory) {
        return Escrow.Config({
            token: address(token),
            admin: admin,
            rakeBeneficiary: rakeBeneficiary,
            depositAmount: DEPOSIT,
            rakeBps: RAKE_BPS,
            fundingDeadline: FUNDING_DEADLINE,
            settlementDeadline: SETTLEMENT_DEADLINE,
            participants: _sorted2(alice, bob)
        });
    }

    function _threePlayerConfig() internal view returns (Escrow.Config memory) {
        return Escrow.Config({
            token: address(token),
            admin: admin,
            rakeBeneficiary: rakeBeneficiary,
            depositAmount: DEPOSIT,
            rakeBps: RAKE_BPS,
            fundingDeadline: FUNDING_DEADLINE,
            settlementDeadline: SETTLEMENT_DEADLINE,
            participants: _sorted3(alice, bob, charlie)
        });
    }

    function _deployEscrow(Escrow.Config memory cfg) internal returns (Escrow escrow) {
        // First participant in sorted order deposits via factory
        address firstParticipant = cfg.participants[0];
        vm.prank(firstParticipant);
        token.approve(address(factory), cfg.depositAmount);
        vm.prank(firstParticipant);
        address addr = factory.createAndDeposit(cfg, bytes32(uint256(1)));
        escrow = Escrow(addr);
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
    // DEPOSIT TESTS
    // ══════════════════════════════════════════════════════════════════════

    function test_deposit_valid() public {
        Escrow escrow = _deployEscrow(_defaultConfig());
        // player1 already deposited via factory
        assertTrue(escrow.hasDeposited(player1));
        assertEq(escrow.depositCount(), 1);
        assertEq(uint256(escrow.status()), uint256(Escrow.Status.FUNDING));
    }

    function test_deposit_autoTransition() public {
        Escrow escrow = _deployEscrow(_defaultConfig());
        // player2 deposits -> should transition to ACTIVE
        vm.prank(player2);
        token.approve(address(escrow), DEPOSIT);
        vm.prank(player2);
        escrow.deposit(player2);

        assertTrue(escrow.hasDeposited(player2));
        assertEq(escrow.depositCount(), 2);
        assertEq(uint256(escrow.status()), uint256(Escrow.Status.ACTIVE));
        assertTrue(escrow.allDeposited());
    }

    function test_deposit_duplicateReverts() public {
        Escrow escrow = _deployEscrow(_defaultConfig());
        // player1 tries to deposit again
        vm.prank(player1);
        token.approve(address(escrow), DEPOSIT);
        vm.prank(player1);
        vm.expectRevert(abi.encodeWithSelector(Escrow.AlreadyDeposited.selector, player1));
        escrow.deposit(player1);
    }

    function test_deposit_nonParticipantReverts() public {
        Escrow escrow = _deployEscrow(_defaultConfig());
        vm.prank(charlie);
        token.approve(address(escrow), DEPOSIT);
        vm.prank(charlie);
        vm.expectRevert(abi.encodeWithSelector(Escrow.NotParticipant.selector, charlie));
        escrow.deposit(charlie);
    }

    function test_deposit_pastDeadlineReverts() public {
        Escrow escrow = _deployEscrow(_defaultConfig());
        vm.warp(FUNDING_DEADLINE + 1);
        vm.prank(player2);
        token.approve(address(escrow), DEPOSIT);
        vm.prank(player2);
        vm.expectRevert(Escrow.FundingDeadlinePassed.selector);
        escrow.deposit(player2);
    }

    function test_deposit_threePlayerAutoTransition() public {
        Escrow.Config memory cfg = _threePlayerConfig();
        Escrow escrow = _deployEscrow(cfg);

        // Second sorted participant deposits -- still FUNDING
        address second = cfg.participants[1];
        vm.prank(second);
        token.approve(address(escrow), DEPOSIT);
        vm.prank(second);
        escrow.deposit(second);
        assertEq(uint256(escrow.status()), uint256(Escrow.Status.FUNDING));

        // Third sorted participant deposits -- transitions to ACTIVE
        address third = cfg.participants[2];
        vm.prank(third);
        token.approve(address(escrow), DEPOSIT);
        vm.prank(third);
        escrow.deposit(third);
        assertEq(uint256(escrow.status()), uint256(Escrow.Status.ACTIVE));
    }

    // ══════════════════════════════════════════════════════════════════════
    // EXPIRE TESTS
    // ══════════════════════════════════════════════════════════════════════

    function test_expire_fromFundingAfterDeadline() public {
        Escrow escrow = _deployEscrow(_defaultConfig());
        vm.warp(FUNDING_DEADLINE + 1);
        escrow.expire();
        assertEq(uint256(escrow.status()), uint256(Escrow.Status.EXPIRED));
    }

    function test_expire_fromActiveAfterDeadline() public {
        Escrow escrow = _deployEscrow(_defaultConfig());
        vm.prank(player2);
        token.approve(address(escrow), DEPOSIT);
        vm.prank(player2);
        escrow.deposit(player2);
        assertEq(uint256(escrow.status()), uint256(Escrow.Status.ACTIVE));

        vm.warp(SETTLEMENT_DEADLINE + 1);
        escrow.expire();
        assertEq(uint256(escrow.status()), uint256(Escrow.Status.EXPIRED));
    }

    function test_expire_beforeDeadlineReverts() public {
        Escrow escrow = _deployEscrow(_defaultConfig());
        vm.expectRevert(Escrow.DeadlineNotPassed.selector);
        escrow.expire();
    }

    function test_expire_activeBeforeSettlementDeadlineReverts() public {
        Escrow escrow = _deployEscrow(_defaultConfig());
        vm.prank(player2);
        token.approve(address(escrow), DEPOSIT);
        vm.prank(player2);
        escrow.deposit(player2);

        vm.warp(FUNDING_DEADLINE + 1); // past funding but before settlement
        vm.expectRevert(Escrow.DeadlineNotPassed.selector);
        escrow.expire();
    }

    // ══════════════════════════════════════════════════════════════════════
    // WITHDRAW TESTS
    // ══════════════════════════════════════════════════════════════════════

    function test_withdraw_onlyExpired() public {
        Escrow escrow = _deployEscrow(_defaultConfig());
        // Not expired yet
        vm.prank(player1);
        vm.expectRevert(
            abi.encodeWithSelector(Escrow.InvalidStatus.selector, Escrow.Status.FUNDING, Escrow.Status.EXPIRED)
        );
        escrow.withdraw();
    }

    function test_withdraw_onlyDepositors() public {
        Escrow escrow = _deployEscrow(_defaultConfig());
        vm.warp(FUNDING_DEADLINE + 1);
        escrow.expire();

        vm.prank(player2); // player2 never deposited
        vm.expectRevert(abi.encodeWithSelector(Escrow.NotDepositor.selector, player2));
        escrow.withdraw();
    }

    function test_withdraw_correctAmount() public {
        Escrow escrow = _deployEscrow(_defaultConfig());
        vm.warp(FUNDING_DEADLINE + 1);
        escrow.expire();

        uint256 balBefore = token.balanceOf(player1);
        vm.prank(player1);
        escrow.withdraw();
        uint256 balAfter = token.balanceOf(player1);

        assertEq(balAfter - balBefore, DEPOSIT);
        // Can't withdraw again
        vm.prank(player1);
        vm.expectRevert(abi.encodeWithSelector(Escrow.NotDepositor.selector, player1));
        escrow.withdraw();
    }

    function test_withdraw_noRake() public {
        Escrow escrow = _deployEscrow(_defaultConfig());
        vm.prank(player2);
        token.approve(address(escrow), DEPOSIT);
        vm.prank(player2);
        escrow.deposit(player2);
        // Both deposited, now expire via settlement deadline
        vm.warp(SETTLEMENT_DEADLINE + 1);
        escrow.expire();

        uint256 rakeBefore = token.balanceOf(rakeBeneficiary);

        vm.prank(player1);
        escrow.withdraw();
        vm.prank(player2);
        escrow.withdraw();

        // Rake beneficiary gets nothing
        assertEq(token.balanceOf(rakeBeneficiary), rakeBefore);
    }

    // ══════════════════════════════════════════════════════════════════════
    // SETTLE TESTS
    // ══════════════════════════════════════════════════════════════════════

    function test_settle_validSignature() public {
        Escrow escrow = _deployEscrow(_defaultConfig());
        vm.prank(player2);
        token.approve(address(escrow), DEPOSIT);
        vm.prank(player2);
        escrow.deposit(player2);

        uint256 balance = token.balanceOf(address(escrow));
        assertEq(balance, DEPOSIT * 2);

        // player1 wins everything
        Escrow.Payout[] memory payouts = new Escrow.Payout[](2);
        payouts[0] = Escrow.Payout(player1, balance);
        payouts[1] = Escrow.Payout(player2, 0);

        bytes memory sig = _signSettlement(escrow, payouts);
        escrow.settle(payouts, sig);

        assertEq(uint256(escrow.status()), uint256(Escrow.Status.SETTLED));

        // player1 gets balance minus rake (2.5%)
        uint256 expectedRake = (balance * RAKE_BPS) / 10_000;
        uint256 expectedNet = balance - expectedRake;
        // player1 started with DEPOSIT*10, deposited DEPOSIT, gets expectedNet back
        assertEq(token.balanceOf(player1), DEPOSIT * 10 - DEPOSIT + expectedNet);
        assertEq(token.balanceOf(rakeBeneficiary), expectedRake);
    }

    function test_settle_invalidSignatureReverts() public {
        Escrow escrow = _deployEscrow(_defaultConfig());
        vm.prank(player2);
        token.approve(address(escrow), DEPOSIT);
        vm.prank(player2);
        escrow.deposit(player2);

        uint256 balance = token.balanceOf(address(escrow));
        Escrow.Payout[] memory payouts = new Escrow.Payout[](2);
        payouts[0] = Escrow.Payout(player1, balance);
        payouts[1] = Escrow.Payout(player2, 0);

        // Sign with wrong key
        (, uint256 wrongPk) = makeAddrAndKey("wrong");
        bytes32 domainSeparator = keccak256(
            abi.encode(
                keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                keccak256("TimeBasedEscrow"),
                keccak256("1"),
                block.chainid,
                address(escrow)
            )
        );
        bytes32[] memory payoutHashes = new bytes32[](2);
        payoutHashes[0] = keccak256(abi.encode(keccak256("Payout(address recipient,uint256 amount)"), player1, balance));
        payoutHashes[1] = keccak256(abi.encode(keccak256("Payout(address recipient,uint256 amount)"), player2, 0));
        bytes32 structHash = keccak256(abi.encode(
            keccak256("Settle(Payout[] payouts)Payout(address recipient,uint256 amount)"),
            keccak256(abi.encodePacked(payoutHashes))
        ));
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", domainSeparator, structHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(wrongPk, digest);

        vm.expectRevert(Escrow.InvalidSignature.selector);
        escrow.settle(payouts, abi.encodePacked(r, s, v));
    }

    function test_settle_wrongPayoutSumReverts() public {
        Escrow escrow = _deployEscrow(_defaultConfig());
        vm.prank(player2);
        token.approve(address(escrow), DEPOSIT);
        vm.prank(player2);
        escrow.deposit(player2);

        // Payouts don't sum to balance
        Escrow.Payout[] memory payouts = new Escrow.Payout[](2);
        payouts[0] = Escrow.Payout(player1, DEPOSIT);
        payouts[1] = Escrow.Payout(player2, DEPOSIT + 1); // off by 1

        bytes memory sig = _signSettlement(escrow, payouts);
        vm.expectRevert(abi.encodeWithSelector(
            Escrow.PayoutSumMismatch.selector, DEPOSIT * 2, DEPOSIT * 2 + 1
        ));
        escrow.settle(payouts, sig);
    }

    function test_settle_nonParticipantRecipientReverts() public {
        Escrow escrow = _deployEscrow(_defaultConfig());
        vm.prank(player2);
        token.approve(address(escrow), DEPOSIT);
        vm.prank(player2);
        escrow.deposit(player2);

        uint256 balance = token.balanceOf(address(escrow));
        Escrow.Payout[] memory payouts = new Escrow.Payout[](2);
        payouts[0] = Escrow.Payout(player1, balance);
        payouts[1] = Escrow.Payout(charlie, 0); // charlie is not a participant

        bytes memory sig = _signSettlement(escrow, payouts);
        vm.expectRevert(abi.encodeWithSelector(Escrow.NotParticipant.selector, charlie));
        escrow.settle(payouts, sig);
    }

    function test_settle_rakeDeduction() public {
        Escrow escrow = _deployEscrow(_defaultConfig());
        vm.prank(player2);
        token.approve(address(escrow), DEPOSIT);
        vm.prank(player2);
        escrow.deposit(player2);

        uint256 balance = token.balanceOf(address(escrow));
        // Split evenly
        Escrow.Payout[] memory payouts = new Escrow.Payout[](2);
        payouts[0] = Escrow.Payout(player1, balance / 2);
        payouts[1] = Escrow.Payout(player2, balance / 2);

        bytes memory sig = _signSettlement(escrow, payouts);
        escrow.settle(payouts, sig);

        uint256 expectedRakePerPlayer = (DEPOSIT * RAKE_BPS) / 10_000;
        uint256 expectedNet = DEPOSIT - expectedRakePerPlayer;
        uint256 totalRake = expectedRakePerPlayer * 2;

        assertEq(token.balanceOf(rakeBeneficiary), totalRake);
        // player1: started DEPOSIT*10, deposited DEPOSIT, got expectedNet back
        assertEq(token.balanceOf(player1), DEPOSIT * 10 - DEPOSIT + expectedNet);
        assertEq(token.balanceOf(player2), DEPOSIT * 10 - DEPOSIT + expectedNet);
    }

    function test_settle_fromFundingState() public {
        // Settlement is valid even from FUNDING (early settlement)
        Escrow escrow = _deployEscrow(_defaultConfig());
        // Only player1 deposited

        uint256 balance = token.balanceOf(address(escrow));
        Escrow.Payout[] memory payouts = new Escrow.Payout[](2);
        payouts[0] = Escrow.Payout(player1, balance);
        payouts[1] = Escrow.Payout(player2, 0);

        bytes memory sig = _signSettlement(escrow, payouts);
        escrow.settle(payouts, sig);

        assertEq(uint256(escrow.status()), uint256(Escrow.Status.SETTLED));
    }

    function test_settle_fromExpiredReverts() public {
        Escrow escrow = _deployEscrow(_defaultConfig());
        vm.warp(FUNDING_DEADLINE + 1);
        escrow.expire();

        Escrow.Payout[] memory payouts = new Escrow.Payout[](2);
        payouts[0] = Escrow.Payout(player1, 0);
        payouts[1] = Escrow.Payout(player2, 0);

        bytes memory sig = _signSettlement(escrow, payouts);
        vm.expectRevert(
            abi.encodeWithSelector(Escrow.InvalidStatus.selector, Escrow.Status.EXPIRED, Escrow.Status.ACTIVE)
        );
        escrow.settle(payouts, sig);
    }

    function test_settle_doubleSettleReverts() public {
        Escrow escrow = _deployEscrow(_defaultConfig());
        vm.prank(player2);
        token.approve(address(escrow), DEPOSIT);
        vm.prank(player2);
        escrow.deposit(player2);

        uint256 balance = token.balanceOf(address(escrow));
        Escrow.Payout[] memory payouts = new Escrow.Payout[](2);
        payouts[0] = Escrow.Payout(player1, balance);
        payouts[1] = Escrow.Payout(player2, 0);

        bytes memory sig = _signSettlement(escrow, payouts);
        escrow.settle(payouts, sig);

        // Second settle should fail
        vm.expectRevert(
            abi.encodeWithSelector(Escrow.InvalidStatus.selector, Escrow.Status.SETTLED, Escrow.Status.ACTIVE)
        );
        escrow.settle(payouts, sig);
    }

    // ══════════════════════════════════════════════════════════════════════
    // CLAIM FAILED TESTS
    // ══════════════════════════════════════════════════════════════════════

    function test_claimFailed_noPendingClaimReverts() public {
        Escrow escrow = _deployEscrow(_defaultConfig());
        vm.prank(player2);
        token.approve(address(escrow), DEPOSIT);
        vm.prank(player2);
        escrow.deposit(player2);

        uint256 balance = token.balanceOf(address(escrow));
        Escrow.Payout[] memory payouts = new Escrow.Payout[](2);
        payouts[0] = Escrow.Payout(player1, balance);
        payouts[1] = Escrow.Payout(player2, 0);

        bytes memory sig = _signSettlement(escrow, payouts);
        escrow.settle(payouts, sig);

        vm.prank(player2);
        vm.expectRevert(abi.encodeWithSelector(Escrow.NoFailedClaim.selector, player2));
        escrow.claimFailed();
    }

    function test_claimFailed_notSettledReverts() public {
        Escrow escrow = _deployEscrow(_defaultConfig());
        vm.prank(player1);
        vm.expectRevert(
            abi.encodeWithSelector(Escrow.InvalidStatus.selector, Escrow.Status.FUNDING, Escrow.Status.SETTLED)
        );
        escrow.claimFailed();
    }

    // ══════════════════════════════════════════════════════════════════════
    // FAILED TRANSFER TEST (with FalseReturnToken)
    // ══════════════════════════════════════════════════════════════════════

    function test_settle_failedTransferStoredForClaim() public {
        FalseReturnToken frt = new FalseReturnToken();
        frt.mint(alice, DEPOSIT * 10);
        frt.mint(bob, DEPOSIT * 10);

        Escrow.Config memory cfg = Escrow.Config({
            token: address(frt),
            admin: admin,
            rakeBeneficiary: rakeBeneficiary,
            depositAmount: DEPOSIT,
            rakeBps: RAKE_BPS,
            fundingDeadline: FUNDING_DEADLINE,
            settlementDeadline: SETTLEMENT_DEADLINE,
            participants: _sorted2(alice, bob)
        });

        vm.prank(player1);
        frt.approve(address(factory), DEPOSIT);
        vm.prank(player1);
        address addr = factory.createAndDeposit(cfg, bytes32(uint256(42)));
        Escrow escrow = Escrow(addr);

        vm.prank(player2);
        frt.approve(address(escrow), DEPOSIT);
        vm.prank(player2);
        escrow.deposit(player2);

        uint256 balance = frt.balanceOf(address(escrow));

        // Block transfers to player1 (but not to rake beneficiary)
        frt.setBlocked(player1, true);

        Escrow.Payout[] memory payouts = new Escrow.Payout[](2);
        payouts[0] = Escrow.Payout(player1, balance);
        payouts[1] = Escrow.Payout(player2, 0);

        bytes memory sig = _signSettlement(escrow, payouts);
        escrow.settle(payouts, sig);

        // player1's payout should be in failedClaims
        uint256 expectedRake = (balance * RAKE_BPS) / 10_000;
        uint256 expectedNet = balance - expectedRake;
        assertEq(escrow.failedClaims(player1), expectedNet);

        // Unblock player1, then claim
        frt.setBlocked(player1, false);
        vm.prank(player1);
        escrow.claimFailed();
        assertEq(escrow.failedClaims(player1), 0);
    }

    // ══════════════════════════════════════════════════════════════════════
    // STATE TRANSITION TESTS
    // ══════════════════════════════════════════════════════════════════════

    function test_noBackwardTransitions() public {
        Escrow escrow = _deployEscrow(_defaultConfig());
        vm.prank(player2);
        token.approve(address(escrow), DEPOSIT);
        vm.prank(player2);
        escrow.deposit(player2);
        assertEq(uint256(escrow.status()), uint256(Escrow.Status.ACTIVE));

        // Can't deposit in ACTIVE state
        vm.prank(player1);
        token.approve(address(escrow), DEPOSIT);
        vm.prank(player1);
        vm.expectRevert(
            abi.encodeWithSelector(Escrow.InvalidStatus.selector, Escrow.Status.ACTIVE, Escrow.Status.FUNDING)
        );
        escrow.deposit(player1);
    }

    // ══════════════════════════════════════════════════════════════════════
    // INITIALIZE VALIDATION TESTS
    // ══════════════════════════════════════════════════════════════════════

    function test_initialize_doubleInitReverts() public {
        Escrow escrow = _deployEscrow(_defaultConfig());
        Escrow.Config memory cfg = _defaultConfig();
        vm.expectRevert(Escrow.AlreadyInitialized.selector);
        escrow.initialize(cfg, address(factory));
    }

    // ══════════════════════════════════════════════════════════════════════
    // VIEW FUNCTIONS
    // ══════════════════════════════════════════════════════════════════════

    function test_getConfig() public {
        Escrow escrow = _deployEscrow(_defaultConfig());
        (
            address token_,
            address admin_,
            address rake_,
            uint256 depositAmt_,
            uint16 rakeBps_,
            uint256 fundDeadline_,
            uint256 settleDeadline_,
            address[] memory participants_
        ) = escrow.getConfig();

        assertEq(token_, address(token));
        assertEq(admin_, admin);
        assertEq(rake_, rakeBeneficiary);
        assertEq(depositAmt_, DEPOSIT);
        assertEq(rakeBps_, RAKE_BPS);
        assertEq(fundDeadline_, FUNDING_DEADLINE);
        assertEq(settleDeadline_, SETTLEMENT_DEADLINE);
        assertEq(participants_.length, 2);
        assertEq(participants_[0], player1);
        assertEq(participants_[1], player2);
    }

    function test_getParticipants() public {
        Escrow escrow = _deployEscrow(_defaultConfig());
        address[] memory p = escrow.getParticipants();
        assertEq(p.length, 2);
        assertEq(p[0], player1);
        assertEq(p[1], player2);
    }

    // ══════════════════════════════════════════════════════════════════════
    // FUZZ TESTS
    // ══════════════════════════════════════════════════════════════════════

    function testFuzz_payoutDistributions(uint256 p1Share) public {
        Escrow escrow = _deployEscrow(_defaultConfig());
        vm.prank(player2);
        token.approve(address(escrow), DEPOSIT);
        vm.prank(player2);
        escrow.deposit(player2);

        uint256 balance = token.balanceOf(address(escrow));
        p1Share = bound(p1Share, 0, balance);
        uint256 p2Share = balance - p1Share;

        Escrow.Payout[] memory payouts = new Escrow.Payout[](2);
        payouts[0] = Escrow.Payout(player1, p1Share);
        payouts[1] = Escrow.Payout(player2, p2Share);

        bytes memory sig = _signSettlement(escrow, payouts);
        escrow.settle(payouts, sig);

        assertEq(uint256(escrow.status()), uint256(Escrow.Status.SETTLED));
    }

    function testFuzz_rakeBps(uint16 bps) public {
        bps = uint16(bound(bps, 0, 10_000));

        Escrow.Config memory cfg = Escrow.Config({
            token: address(token),
            admin: admin,
            rakeBeneficiary: rakeBeneficiary,
            depositAmount: DEPOSIT,
            rakeBps: bps,
            fundingDeadline: FUNDING_DEADLINE,
            settlementDeadline: SETTLEMENT_DEADLINE,
            participants: _sorted2(alice, bob)
        });

        vm.prank(player1);
        token.approve(address(factory), DEPOSIT);
        vm.prank(player1);
        address addr = factory.createAndDeposit(cfg, bytes32(uint256(bps)));
        Escrow escrow = Escrow(addr);

        vm.prank(player2);
        token.approve(address(escrow), DEPOSIT);
        vm.prank(player2);
        escrow.deposit(player2);

        uint256 balance = token.balanceOf(address(escrow));
        Escrow.Payout[] memory payouts = new Escrow.Payout[](2);
        payouts[0] = Escrow.Payout(player1, balance);
        payouts[1] = Escrow.Payout(player2, 0);

        bytes memory sig = _signSettlement(escrow, payouts);
        escrow.settle(payouts, sig);

        uint256 expectedRake = (balance * bps) / 10_000;
        assertEq(token.balanceOf(rakeBeneficiary), expectedRake);
    }

    function testFuzz_depositOrdering(bool secondFirst) public {
        Escrow.Config memory cfg = _threePlayerConfig();
        address first = cfg.participants[0];
        address second = cfg.participants[1];
        address third = cfg.participants[2];

        vm.prank(first);
        token.approve(address(factory), DEPOSIT);
        vm.prank(first);
        address addr = factory.createAndDeposit(cfg, bytes32(uint256(99)));
        Escrow escrow = Escrow(addr);

        if (secondFirst) {
            vm.prank(second);
            token.approve(address(escrow), DEPOSIT);
            vm.prank(second);
            escrow.deposit(second);

            vm.prank(third);
            token.approve(address(escrow), DEPOSIT);
            vm.prank(third);
            escrow.deposit(third);
        } else {
            vm.prank(third);
            token.approve(address(escrow), DEPOSIT);
            vm.prank(third);
            escrow.deposit(third);

            vm.prank(second);
            token.approve(address(escrow), DEPOSIT);
            vm.prank(second);
            escrow.deposit(second);
        }

        assertEq(uint256(escrow.status()), uint256(Escrow.Status.ACTIVE));
        assertTrue(escrow.allDeposited());
    }

    function testFuzz_timestamps(uint256 fundDeadline, uint256 warpTo) public {
        // Constrain to valid range
        fundDeadline = bound(fundDeadline, block.timestamp + 1, block.timestamp + 365 days);
        uint256 settleDeadline = fundDeadline + 1 days;
        warpTo = bound(warpTo, block.timestamp, fundDeadline + 2);

        Escrow.Config memory cfg = Escrow.Config({
            token: address(token),
            admin: admin,
            rakeBeneficiary: rakeBeneficiary,
            depositAmount: DEPOSIT,
            rakeBps: RAKE_BPS,
            fundingDeadline: fundDeadline,
            settlementDeadline: settleDeadline,
            participants: _sorted2(alice, bob)
        });

        vm.prank(player1);
        token.approve(address(factory), DEPOSIT);
        vm.prank(player1);
        address addr = factory.createAndDeposit(cfg, bytes32(uint256(fundDeadline)));
        Escrow escrow = Escrow(addr);

        vm.warp(warpTo);

        if (warpTo > fundDeadline) {
            // Should be expirable
            escrow.expire();
            assertEq(uint256(escrow.status()), uint256(Escrow.Status.EXPIRED));
        } else {
            // Should not be expirable
            vm.expectRevert(Escrow.DeadlineNotPassed.selector);
            escrow.expire();
        }
    }
}
