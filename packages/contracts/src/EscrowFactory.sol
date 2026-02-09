// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {LibClone} from "solady/utils/LibClone.sol";
import {SafeTransferLib} from "solady/utils/SafeTransferLib.sol";
import {Escrow} from "./Escrow.sol";
import {ISignatureTransfer} from "./interfaces/ISignatureTransfer.sol";

/// @title Escrow Factory
/// @notice Deploys minimal proxies (EIP-1167) of Escrow via CREATE2.
///         First depositor uses `createAndDeposit` for atomic deploy + deposit.
contract EscrowFactory {
    address public immutable IMPLEMENTATION;

    /// @dev Canonical Permit2 contract (same address on all EVM chains)
    address private constant PERMIT2 = 0x000000000022D473030F116dDEE9F6B43aC78BA3;

    error DepositTransferMismatch(uint256 expected, uint256 actual);

    event EscrowCreated(address indexed escrow, bytes32 indexed salt);

    constructor(address implementation_) {
        IMPLEMENTATION = implementation_;
    }

    /// @notice Deploy a new escrow proxy and execute the first deposit atomically.
    ///         Caller must have approved this factory for `config.depositAmount` of `config.token`.
    /// @param config Escrow configuration (participants, token, deadlines, etc.)
    /// @param salt Unique salt for CREATE2 deterministic address
    /// @return escrow Address of the deployed escrow proxy
    function createAndDeposit(Escrow.Config calldata config, bytes32 salt) external returns (address escrow) {
        // Deploy minimal proxy via CREATE2
        bytes32 finalSalt = _computeSalt(config, salt);
        escrow = LibClone.cloneDeterministic(IMPLEMENTATION, finalSalt);

        // Initialize the escrow
        Escrow(escrow).initialize(config, address(this));

        emit EscrowCreated(escrow, salt);

        // Transfer tokens from caller to escrow and verify received amount
        uint256 balBefore = SafeTransferLib.balanceOf(config.token, escrow);
        SafeTransferLib.safeTransferFrom(config.token, msg.sender, escrow, config.depositAmount);
        uint256 balAfter = SafeTransferLib.balanceOf(config.token, escrow);
        if (balAfter - balBefore != config.depositAmount) {
            revert DepositTransferMismatch(config.depositAmount, balAfter - balBefore);
        }
        Escrow(escrow).recordDeposit(msg.sender);
    }

    /// @notice Deploy a new escrow proxy and execute the first deposit via Permit2.
    ///         No prior ERC-20 approval needed (only Permit2 allowance).
    ///         Tokens flow directly from caller to escrow via Permit2.
    /// @param config Escrow configuration (participants, token, deadlines, etc.)
    /// @param salt Unique salt for CREATE2 deterministic address
    /// @param permit Permit2 transfer parameters (token, amount, nonce, deadline)
    /// @param signature The EIP-712 signature over the Permit2 transfer
    /// @return escrow Address of the deployed escrow proxy
    function createAndDepositWithPermit2(
        Escrow.Config calldata config,
        bytes32 salt,
        ISignatureTransfer.PermitTransferFrom calldata permit,
        bytes calldata signature
    ) external returns (address escrow) {
        bytes32 finalSalt = _computeSalt(config, salt);
        escrow = LibClone.cloneDeterministic(IMPLEMENTATION, finalSalt);
        Escrow(escrow).initialize(config, address(this));
        emit EscrowCreated(escrow, salt);

        // Permit2 transfers tokens directly from caller to escrow
        uint256 balBefore = SafeTransferLib.balanceOf(config.token, escrow);
        ISignatureTransfer(PERMIT2)
            .permitTransferFrom(
                permit,
                ISignatureTransfer.SignatureTransferDetails({to: escrow, requestedAmount: config.depositAmount}),
                msg.sender,
                signature
            );
        uint256 balAfter = SafeTransferLib.balanceOf(config.token, escrow);
        if (balAfter - balBefore != config.depositAmount) {
            revert DepositTransferMismatch(config.depositAmount, balAfter - balBefore);
        }

        Escrow(escrow).recordDeposit(msg.sender);
    }

    /// @notice Compute the deterministic address for a given config + salt.
    function getEscrowAddress(Escrow.Config calldata config, bytes32 salt) external view returns (address) {
        bytes32 finalSalt = _computeSalt(config, salt);
        return LibClone.predictDeterministicAddress(IMPLEMENTATION, finalSalt, address(this));
    }

    /// @dev Combine config hash with user salt for CREATE2 uniqueness.
    function _computeSalt(Escrow.Config calldata config, bytes32 salt) private pure returns (bytes32) {
        return keccak256(
            abi.encode(
                config.token,
                config.admin,
                config.rakeBeneficiary,
                config.depositAmount,
                config.rakeBps,
                config.fundingDeadline,
                config.settlementDeadline,
                keccak256(abi.encodePacked(config.participants)),
                salt
            )
        );
    }
}
