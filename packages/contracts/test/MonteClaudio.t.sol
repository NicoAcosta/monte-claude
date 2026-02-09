// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {MonteClaudio} from "../src/MonteClaudio.sol";

contract MonteClaudioTest is Test {
    MonteClaudio token;
    address alice = makeAddr("alice");
    address bob = makeAddr("bob");

    function setUp() public {
        token = new MonteClaudio();
    }

    // ── Metadata ──────────────────────────────────────────────

    function test_name() public view {
        assertEq(token.name(), "MonteClaudio");
    }

    function test_symbol() public view {
        assertEq(token.symbol(), "MONTE");
    }

    function test_decimals() public view {
        assertEq(token.decimals(), 18);
    }

    function test_initialSupplyIsZero() public view {
        assertEq(token.totalSupply(), 0);
    }

    // ── Faucet ────────────────────────────────────────────────

    function test_faucet_mintsCorrectAmount() public {
        vm.prank(alice);
        token.faucet();

        assertEq(token.balanceOf(alice), 10_000e18);
        assertEq(token.totalSupply(), 10_000e18);
    }

    function test_faucet_emitsEvent() public {
        vm.expectEmit(true, false, false, true);
        emit MonteClaudio.FaucetClaimed(alice, 10_000e18);

        vm.prank(alice);
        token.faucet();
    }

    function test_faucet_setsLastClaimed() public {
        uint256 t = block.timestamp;
        vm.prank(alice);
        token.faucet();

        assertEq(token.lastClaimed(alice), t);
    }

    function test_faucet_revertsBeforeCooldown() public {
        vm.prank(alice);
        token.faucet();

        // Try again immediately
        vm.prank(alice);
        vm.expectRevert(
            abi.encodeWithSelector(
                MonteClaudio.CooldownNotElapsed.selector,
                block.timestamp + 1 days
            )
        );
        token.faucet();
    }

    function test_faucet_worksAfterCooldown() public {
        vm.prank(alice);
        token.faucet();

        vm.warp(block.timestamp + 1 days);

        vm.prank(alice);
        token.faucet();

        assertEq(token.balanceOf(alice), 20_000e18);
    }

    function test_faucet_independentPerUser() public {
        vm.prank(alice);
        token.faucet();

        // Bob can claim immediately even though Alice just claimed
        vm.prank(bob);
        token.faucet();

        assertEq(token.balanceOf(alice), 10_000e18);
        assertEq(token.balanceOf(bob), 10_000e18);
    }

    function test_faucet_firstClaimAlwaysWorks() public {
        // Warp to a non-zero timestamp to be realistic
        vm.warp(1_700_000_000);

        vm.prank(alice);
        token.faucet(); // Should not revert — lastClaimed[alice] is 0

        assertEq(token.balanceOf(alice), 10_000e18);
    }

    // ── Permit2 Allowance ─────────────────────────────────────

    function test_allowance_returnsMaxForPermit2() public view {
        assertEq(
            token.allowance(alice, token.PERMIT2()),
            type(uint256).max
        );
    }

    function test_allowance_returnsNormalForOthers() public view {
        assertEq(token.allowance(alice, bob), 0);
    }

    function test_allowance_normalApproveStillWorks() public {
        vm.prank(alice);
        token.approve(bob, 500e18);

        assertEq(token.allowance(alice, bob), 500e18);
    }

    // ── Burnable ──────────────────────────────────────────────

    function test_burn() public {
        vm.prank(alice);
        token.faucet();

        vm.prank(alice);
        token.burn(1_000e18);

        assertEq(token.balanceOf(alice), 9_000e18);
    }

    function test_burnFrom() public {
        vm.prank(alice);
        token.faucet();

        vm.prank(alice);
        token.approve(bob, 2_000e18);

        vm.prank(bob);
        token.burnFrom(alice, 2_000e18);

        assertEq(token.balanceOf(alice), 8_000e18);
    }

    // ── Fuzz ──────────────────────────────────────────────────

    function testFuzz_faucetCooldown(uint256 elapsed) public {
        vm.warp(1_700_000_000); // realistic timestamp

        vm.prank(alice);
        token.faucet();

        elapsed = bound(elapsed, 0, 2 days);
        vm.warp(block.timestamp + elapsed);

        if (elapsed < 1 days) {
            vm.prank(alice);
            vm.expectRevert();
            token.faucet();
        } else {
            vm.prank(alice);
            token.faucet();
            assertEq(token.balanceOf(alice), 20_000e18);
        }
    }

    function testFuzz_permit2AlwaysMax(address owner) public view {
        assertEq(
            token.allowance(owner, token.PERMIT2()),
            type(uint256).max
        );
    }
}
