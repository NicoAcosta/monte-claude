// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {Escrow} from "../src/Escrow.sol";
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// @dev Simple ERC20 for testing
contract MockERC20 is ERC20 {
    constructor() ERC20("Mock", "MCK") {}
    function mint(address to, uint256 amount) external { _mint(to, amount); }
}

/// @dev Shared helpers for escrow test suites
abstract contract BaseEscrowTest is Test {
    /// @dev Sort 2 addresses ascending (contract requires sorted participants)
    function _sorted2(address a, address b) internal pure returns (address[] memory) {
        address[] memory arr = new address[](2);
        if (uint160(a) < uint160(b)) {
            arr[0] = a; arr[1] = b;
        } else {
            arr[0] = b; arr[1] = a;
        }
        return arr;
    }

    /// @dev Sort 3 addresses ascending
    function _sorted3(address a, address b, address c) internal pure returns (address[] memory) {
        address[] memory arr = new address[](3);
        arr[0] = a; arr[1] = b; arr[2] = c;
        // Bubble sort 3 elements
        if (uint160(arr[0]) > uint160(arr[1])) (arr[0], arr[1]) = (arr[1], arr[0]);
        if (uint160(arr[1]) > uint160(arr[2])) (arr[1], arr[2]) = (arr[2], arr[1]);
        if (uint160(arr[0]) > uint160(arr[1])) (arr[0], arr[1]) = (arr[1], arr[0]);
        return arr;
    }

    /// @dev Sign an EIP-712 settlement with the given private key
    function _signSettlement(Escrow escrow, Escrow.Payout[] memory payouts, uint256 pk)
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
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(pk, digest);
        return abi.encodePacked(r, s, v);
    }
}
