// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {Escrow} from "../src/Escrow.sol";
import {ISignatureTransfer} from "../src/interfaces/ISignatureTransfer.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";

/// @dev Simple ERC20 for testing
contract MockERC20 is ERC20 {
    constructor() ERC20("Mock", "MCK") {}

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}

/// @dev Minimal Permit2 mock implementing SignatureTransfer with proper EIP-712 verification.
///      Uses the same domain separator and typehashes as the canonical Permit2 contract.
contract MockPermit2 is ISignatureTransfer {
    bytes32 private constant _DOMAIN_TYPEHASH =
        keccak256("EIP712Domain(string name,uint256 chainId,address verifyingContract)");
    bytes32 private constant _NAME_HASH = keccak256("Permit2");
    bytes32 private constant _TOKEN_PERMISSIONS_TYPEHASH = keccak256("TokenPermissions(address token,uint256 amount)");
    bytes32 private constant _PERMIT_TRANSFER_FROM_TYPEHASH = keccak256(
        "PermitTransferFrom(TokenPermissions permitted,address spender,uint256 nonce,uint256 deadline)TokenPermissions(address token,uint256 amount)"
    );

    /// @dev Tracks used nonces per owner (bitmap: word index -> bitmap)
    mapping(address => mapping(uint248 => uint256)) private _nonceBitmap;

    error InvalidSigner();
    error SignatureExpired(uint256 deadline);
    error InvalidNonce();

    function DOMAIN_SEPARATOR() public view returns (bytes32) {
        return keccak256(abi.encode(_DOMAIN_TYPEHASH, _NAME_HASH, block.chainid, address(this)));
    }

    function permitTransferFrom(
        PermitTransferFrom memory permit,
        SignatureTransferDetails calldata transferDetails,
        address owner,
        bytes calldata signature
    ) external override {
        if (block.timestamp > permit.deadline) {
            revert SignatureExpired(permit.deadline);
        }

        // Use and invalidate nonce
        _useNonce(owner, permit.nonce);

        // Verify signature (spender = msg.sender, NOT in the struct but in the hash)
        bytes32 tokenPermissionsHash =
            keccak256(abi.encode(_TOKEN_PERMISSIONS_TYPEHASH, permit.permitted.token, permit.permitted.amount));
        bytes32 structHash = keccak256(
            abi.encode(
                _PERMIT_TRANSFER_FROM_TYPEHASH,
                tokenPermissionsHash,
                msg.sender, // spender
                permit.nonce,
                permit.deadline
            )
        );
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", DOMAIN_SEPARATOR(), structHash));
        address signer = ECDSA.recover(digest, signature);
        if (signer != owner) revert InvalidSigner();

        // Execute transfer
        IERC20(permit.permitted.token).transferFrom(owner, transferDetails.to, transferDetails.requestedAmount);
    }

    function _useNonce(address owner, uint256 nonce) private {
        uint248 wordIndex = uint248(nonce >> 8);
        uint8 bitIndex = uint8(nonce);
        uint256 bit = 1 << bitIndex;
        uint256 word = _nonceBitmap[owner][wordIndex];
        if (word & bit != 0) revert InvalidNonce();
        _nonceBitmap[owner][wordIndex] = word | bit;
    }
}

/// @dev Shared helpers for escrow test suites
abstract contract BaseEscrowTest is Test {
    address internal constant PERMIT2_ADDRESS = 0x000000000022D473030F116dDEE9F6B43aC78BA3;

    // Permit2 EIP-712 typehashes (must match MockPermit2)
    bytes32 private constant _PERMIT2_DOMAIN_TYPEHASH =
        keccak256("EIP712Domain(string name,uint256 chainId,address verifyingContract)");
    bytes32 private constant _PERMIT2_NAME_HASH = keccak256("Permit2");
    bytes32 private constant _TOKEN_PERMISSIONS_TYPEHASH = keccak256("TokenPermissions(address token,uint256 amount)");
    bytes32 private constant _PERMIT_TRANSFER_FROM_TYPEHASH = keccak256(
        "PermitTransferFrom(TokenPermissions permitted,address spender,uint256 nonce,uint256 deadline)TokenPermissions(address token,uint256 amount)"
    );

    /// @dev Sort 2 addresses ascending (contract requires sorted participants)
    function _sorted2(address a, address b) internal pure returns (address[] memory) {
        address[] memory arr = new address[](2);
        if (uint160(a) < uint160(b)) {
            arr[0] = a;
            arr[1] = b;
        } else {
            arr[0] = b;
            arr[1] = a;
        }
        return arr;
    }

    /// @dev Sort 3 addresses ascending
    function _sorted3(address a, address b, address c) internal pure returns (address[] memory) {
        address[] memory arr = new address[](3);
        arr[0] = a;
        arr[1] = b;
        arr[2] = c;
        // Bubble sort 3 elements
        if (uint160(arr[0]) > uint160(arr[1])) (arr[0], arr[1]) = (arr[1], arr[0]);
        if (uint160(arr[1]) > uint160(arr[2])) (arr[1], arr[2]) = (arr[2], arr[1]);
        if (uint160(arr[0]) > uint160(arr[1])) (arr[0], arr[1]) = (arr[1], arr[0]);
        return arr;
    }

    /// @dev Sign an EIP-712 settlement with the given private key (dev mode: no pcr0)
    function _signSettlement(Escrow escrow, Escrow.Payout[] memory payouts, uint256 pk)
        internal
        view
        returns (bytes memory)
    {
        return _signSettlement(escrow, payouts, bytes(""), pk);
    }

    /// @dev Sign an EIP-712 settlement with pcr0 included in the signed message
    function _signSettlement(Escrow escrow, Escrow.Payout[] memory payouts, bytes memory pcr0, uint256 pk)
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
                    keccak256("Payout(address recipient,uint256 amount)"), payouts[i].recipient, payouts[i].amount
                )
            );
        }
        bytes32 structHash = keccak256(
            abi.encode(
                keccak256("Settle(Payout[] payouts,bytes pcr0)Payout(address recipient,uint256 amount)"),
                keccak256(abi.encodePacked(payoutHashes)),
                keccak256(pcr0)
            )
        );

        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", domainSeparator, structHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(pk, digest);
        return abi.encodePacked(r, s, v);
    }

    // ── Factory admin signature helpers ─────────────────────────

    bytes32 private constant _FACTORY_DOMAIN_TYPEHASH =
        keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)");
    bytes32 private constant _FACTORY_NAME_HASH = keccak256("EscrowFactory");
    bytes32 private constant _FACTORY_VERSION_HASH = keccak256("1");
    bytes32 private constant _CREATE_ESCROW_TYPEHASH = keccak256(
        "CreateEscrow(address token,address admin,address rakeBeneficiary,uint256 depositAmount,uint16 rakeBps,uint256 fundingDeadline,uint256 settlementDeadline,bytes32 participantsHash,bytes32 pcr0Hash,bytes32 salt)"
    );

    /// @dev Sign an EIP-712 CreateEscrow message for factory admin verification.
    function _signCreateEscrow(
        address factoryAddr,
        Escrow.Config memory config,
        bytes32 salt,
        uint256 pk
    ) internal view returns (bytes memory) {
        bytes32 domainSeparator = keccak256(
            abi.encode(_FACTORY_DOMAIN_TYPEHASH, _FACTORY_NAME_HASH, _FACTORY_VERSION_HASH, block.chainid, factoryAddr)
        );

        bytes32 participantsHash = keccak256(abi.encodePacked(config.participants));

        bytes32 structHash = keccak256(
            abi.encode(
                _CREATE_ESCROW_TYPEHASH,
                config.token,
                config.admin,
                config.rakeBeneficiary,
                config.depositAmount,
                config.rakeBps,
                config.fundingDeadline,
                config.settlementDeadline,
                participantsHash,
                config.pcr0Hash,
                salt
            )
        );

        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", domainSeparator, structHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(pk, digest);
        return abi.encodePacked(r, s, v);
    }

    // ── Permit2 helpers ───────────────────────────────────────────────────

    /// @dev Deploy MockPermit2 and etch its code at the canonical Permit2 address.
    ///      MockPermit2 computes its domain separator dynamically from block.chainid,
    ///      avoiding the immutable/cached value issues of the precompiled bytecode approach.
    function _deployPermit2() internal {
        MockPermit2 mock = new MockPermit2();
        vm.etch(PERMIT2_ADDRESS, address(mock).code);
    }

    /// @dev Sign a Permit2 single-token transfer. Returns the EIP-712 signature.
    ///      Permit2's PermitTransferFrom typehash includes `spender` in the hash
    ///      but NOT in the struct (Permit2 design -- spender = contract calling permitTransferFrom).
    function _signPermit2Transfer(
        ISignatureTransfer.PermitTransferFrom memory permit,
        uint256 privateKey,
        address spender
    ) internal view returns (bytes memory) {
        bytes32 permit2DomainSeparator = keccak256(
            abi.encode(_PERMIT2_DOMAIN_TYPEHASH, _PERMIT2_NAME_HASH, block.chainid, PERMIT2_ADDRESS)
        );

        bytes32 tokenPermissionsHash =
            keccak256(abi.encode(_TOKEN_PERMISSIONS_TYPEHASH, permit.permitted.token, permit.permitted.amount));

        bytes32 structHash = keccak256(
            abi.encode(_PERMIT_TRANSFER_FROM_TYPEHASH, tokenPermissionsHash, spender, permit.nonce, permit.deadline)
        );

        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", permit2DomainSeparator, structHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(privateKey, digest);
        return abi.encodePacked(r, s, v);
    }
}
