// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {ERC20Burnable} from "@openzeppelin/contracts/token/ERC20/extensions/ERC20Burnable.sol";
import {ERC20Permit} from "@openzeppelin/contracts/token/ERC20/extensions/ERC20Permit.sol";

/// @title MonteClaudio (MONTE)
/// @notice Ownerless casino token with a daily faucet and native Permit2 support.
/// @dev No admin functions. All parameters are immutable from deployment.
contract MonteClaudio is ERC20, ERC20Burnable, ERC20Permit {
    /// @notice Canonical Permit2 deployment address (same on all EVM chains).
    address public constant PERMIT2 = 0x000000000022D473030F116dDEE9F6B43aC78BA3;

    /// @notice Tokens minted per faucet claim.
    uint256 public constant FAUCET_AMOUNT = 10_000e18;

    /// @notice Minimum time between claims for a single address.
    uint256 public constant COOLDOWN = 1 days;

    /// @notice Timestamp of each address's last faucet claim.
    mapping(address => uint256) public lastClaimed;

    error CooldownNotElapsed(uint256 availableAt);

    event FaucetClaimed(address indexed claimer, uint256 amount);

    constructor() ERC20("MonteClaudio", "MONTE") ERC20Permit("MonteClaudio") {}

    /// @notice Mint FAUCET_AMOUNT to caller. Callable once per COOLDOWN period.
    function faucet() external {
        uint256 last = lastClaimed[msg.sender];
        if (last != 0) {
            uint256 availableAt = last + COOLDOWN;
            if (block.timestamp < availableAt) revert CooldownNotElapsed(availableAt);
        }

        lastClaimed[msg.sender] = block.timestamp;
        _mint(msg.sender, FAUCET_AMOUNT);

        emit FaucetClaimed(msg.sender, FAUCET_AMOUNT);
    }

    /// @notice Returns max allowance for Permit2 so users never need an approval tx.
    function allowance(address owner, address spender) public view override returns (uint256) {
        if (spender == PERMIT2) return type(uint256).max;
        return super.allowance(owner, spender);
    }
}
