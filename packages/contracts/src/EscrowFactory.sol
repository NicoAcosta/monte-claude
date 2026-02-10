// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {LibClone} from "solady/utils/LibClone.sol";
import {SafeTransferLib} from "solady/utils/SafeTransferLib.sol";
import {ECDSA} from "solady/utils/ECDSA.sol";
import {Escrow} from "./Escrow.sol";
import {ISignatureTransfer} from "./interfaces/ISignatureTransfer.sol";

/// @title Escrow Factory
/// @notice Deploys minimal proxies (EIP-1167) of Escrow via CREATE2.
///         First depositor uses `createAndDeposit` for atomic deploy + deposit.
///         Admin must sign each config+salt via EIP-712 before deployment.
contract EscrowFactory {
    address public immutable IMPLEMENTATION;

    /// @dev Canonical Permit2 contract (same address on all EVM chains)
    address private constant PERMIT2 = 0x000000000022D473030F116dDEE9F6B43aC78BA3;

    // ── EIP-712 constants ────────────────────────────────────────────────

    bytes32 private constant DOMAIN_TYPEHASH =
        keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)");
    bytes32 private constant NAME_HASH = keccak256("EscrowFactory");
    bytes32 private constant VERSION_HASH = keccak256("1");

    bytes32 private constant CREATE_ESCROW_TYPEHASH = keccak256(
        "CreateEscrow(address token,address admin,address rakeBeneficiary,uint256 depositAmount,uint16 rakeBps,uint256 fundingDeadline,uint256 settlementDeadline,bytes32 participantsHash,bytes32 pcr0Hash,bytes32 salt)"
    );

    // ── Errors ───────────────────────────────────────────────────────────

    error DepositTransferMismatch(uint256 expected, uint256 actual);
    error InvalidAdminSignature();

    event EscrowCreated(address indexed escrow, bytes32 indexed salt);

    constructor(address implementation_) {
        IMPLEMENTATION = implementation_;
    }

    /// @notice Deploy a new escrow proxy and execute the first deposit atomically.
    ///         Caller must have approved this factory for `config.depositAmount` of `config.token`.
    ///         Admin must have signed the config+salt via EIP-712.
    /// @param config Escrow configuration (participants, token, deadlines, etc.)
    /// @param salt Unique salt for CREATE2 deterministic address
    /// @param adminSignature EIP-712 signature from config.admin over the config+salt
    /// @return escrow Address of the deployed escrow proxy
    function createAndDeposit(Escrow.Config calldata config, bytes32 salt, bytes calldata adminSignature)
        external
        returns (address escrow)
    {
        _verifyAdminSignature(config, salt, adminSignature);

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
    ///         Admin must have signed the config+salt via EIP-712.
    /// @param config Escrow configuration (participants, token, deadlines, etc.)
    /// @param salt Unique salt for CREATE2 deterministic address
    /// @param adminSignature EIP-712 signature from config.admin over the config+salt
    /// @param permit Permit2 transfer parameters (token, amount, nonce, deadline)
    /// @param signature The EIP-712 signature over the Permit2 transfer
    /// @return escrow Address of the deployed escrow proxy
    function createAndDepositWithPermit2(
        Escrow.Config calldata config,
        bytes32 salt,
        bytes calldata adminSignature,
        ISignatureTransfer.PermitTransferFrom calldata permit,
        bytes calldata signature
    ) external returns (address escrow) {
        _verifyAdminSignature(config, salt, adminSignature);

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

    // ── Internal ─────────────────────────────────────────────────────────

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
                config.pcr0Hash,
                salt
            )
        );
    }

    function _domainSeparator() private view returns (bytes32) {
        return keccak256(abi.encode(DOMAIN_TYPEHASH, NAME_HASH, VERSION_HASH, block.chainid, address(this)));
    }

    function _hashTypedData(bytes32 structHash) private view returns (bytes32) {
        return keccak256(abi.encodePacked("\x19\x01", _domainSeparator(), structHash));
    }

    function _hashCreateEscrow(Escrow.Config calldata config, bytes32 salt) private pure returns (bytes32) {
        return keccak256(
            abi.encode(
                CREATE_ESCROW_TYPEHASH,
                config.token,
                config.admin,
                config.rakeBeneficiary,
                config.depositAmount,
                config.rakeBps,
                config.fundingDeadline,
                config.settlementDeadline,
                keccak256(abi.encodePacked(config.participants)),
                config.pcr0Hash,
                salt
            )
        );
    }

    function _verifyAdminSignature(Escrow.Config calldata config, bytes32 salt, bytes calldata adminSignature)
        private
        view
    {
        bytes32 structHash = _hashCreateEscrow(config, salt);
        bytes32 digest = _hashTypedData(structHash);
        address signer = ECDSA.recoverCalldata(digest, adminSignature);
        if (signer != config.admin) revert InvalidAdminSignature();
    }
}
