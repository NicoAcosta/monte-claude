// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeTransferLib} from "solady/utils/SafeTransferLib.sol";
import {ECDSA} from "solady/utils/ECDSA.sol";
import {ReentrancyGuard} from "solady/utils/ReentrancyGuard.sol";
import {EnumerableSetLib} from "solady/utils/EnumerableSetLib.sol";
import {ISignatureTransfer} from "./interfaces/ISignatureTransfer.sol";

/// @title Time-Based Escrow
/// @notice Generic multi-party escrow with EIP-712 signed settlement.
///         Knows nothing about poker — reusable for any game or competition.
contract Escrow is ReentrancyGuard {
    using EnumerableSetLib for EnumerableSetLib.AddressSet;

    // ── Types ────────────────────────────────────────────────────────────

    enum Status { FUNDING, ACTIVE, SETTLED, EXPIRED }

    struct Config {
        address token;
        address admin;
        address rakeBeneficiary;
        uint256 depositAmount;
        uint16  rakeBps;
        uint256 fundingDeadline;
        uint256 settlementDeadline;
        address[] participants;
    }

    struct Payout {
        address recipient;
        uint256 amount;
    }

    // ── EIP-712 constants ────────────────────────────────────────────────

    bytes32 private constant DOMAIN_TYPEHASH =
        keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)");
    bytes32 private constant NAME_HASH   = keccak256("TimeBasedEscrow");
    bytes32 private constant VERSION_HASH = keccak256("1");

    bytes32 private constant PAYOUT_TYPEHASH =
        keccak256("Payout(address recipient,uint256 amount)");
    bytes32 private constant SETTLE_TYPEHASH =
        keccak256("Settle(Payout[] payouts)Payout(address recipient,uint256 amount)");

    uint16 private constant MAX_BPS = 10_000;

    /// @dev Canonical Permit2 contract (same address on all EVM chains)
    address private constant PERMIT2 = 0x000000000022D473030F116dDEE9F6B43aC78BA3;

    // ── Storage ──────────────────────────────────────────────────────────

    bool    public initialized;
    Status  public status;
    address public factory;

    // Config fields (set once in initialize)
    address public token;
    address public admin;
    address public rakeBeneficiary;
    uint256 public depositAmount;
    uint16  public rakeBps;
    uint256 public fundingDeadline;
    uint256 public settlementDeadline;

    /// @dev O(1) contains/add/remove via Solady EnumerableSetLib
    EnumerableSetLib.AddressSet private _participants;

    // Deposit tracking
    mapping(address => bool) public hasDeposited;
    uint256 public depositCount;
    uint256 public participantCount;

    // Failed settlement claims
    mapping(address => uint256) public failedClaims;

    // ── Events ───────────────────────────────────────────────────────────

    event Deposited(address indexed participant, uint256 amount);
    event StatusChanged(Status indexed from, Status indexed to);
    event Settled(uint256 totalPayout, uint256 rake);
    event Withdrawn(address indexed participant, uint256 amount);
    event FailedTransfer(address indexed recipient, uint256 amount);
    event ClaimedFailed(address indexed recipient, uint256 amount);

    // ── Errors ───────────────────────────────────────────────────────────

    error AlreadyInitialized();
    error NotFactory();
    error NotParticipant(address addr);
    error AlreadyDeposited(address addr);
    error FundingDeadlinePassed();
    error InvalidStatus(Status current, Status required);
    error DeadlineNotPassed();
    error NotDepositor(address addr);
    error InvalidSignature();
    error PayoutSumMismatch(uint256 expected, uint256 actual);
    error NoFailedClaim(address addr);
    error DepositTransferMismatch(uint256 expected, uint256 actual);
    error InvalidConfig();
    error ParticipantsNotSorted();

    // ── Modifiers ────────────────────────────────────────────────────────

    modifier onlyStatus(Status required) {
        _requireStatus(required);
        _;
    }

    modifier onlyFactory() {
        _requireFactory();
        _;
    }

    function _requireStatus(Status required) private view {
        if (status != required) revert InvalidStatus(status, required);
    }

    function _requireFactory() private view {
        if (msg.sender != factory) revert NotFactory();
    }

    // ── Initialize ───────────────────────────────────────────────────────

    /// @notice Called once by factory immediately after proxy deployment.
    function initialize(Config calldata cfg, address factory_) external {
        if (initialized) revert AlreadyInitialized();
        if (cfg.token == address(0)) revert InvalidConfig();
        if (cfg.admin == address(0)) revert InvalidConfig();
        if (cfg.rakeBeneficiary == address(0)) revert InvalidConfig();
        if (cfg.participants.length == 0) revert InvalidConfig();
        if (cfg.fundingDeadline <= block.timestamp) revert InvalidConfig();
        if (cfg.settlementDeadline <= cfg.fundingDeadline) revert InvalidConfig();
        if (cfg.depositAmount == 0) revert InvalidConfig();
        if (cfg.rakeBps >= MAX_BPS) revert InvalidConfig();

        initialized = true;
        factory = factory_;

        token               = cfg.token;
        admin               = cfg.admin;
        rakeBeneficiary     = cfg.rakeBeneficiary;
        depositAmount       = cfg.depositAmount;
        rakeBps             = cfg.rakeBps;
        fundingDeadline     = cfg.fundingDeadline;
        settlementDeadline  = cfg.settlementDeadline;

        uint256 len = cfg.participants.length;
        // Invariant: participants must be sorted ascending by address (deterministic ordering)
        for (uint256 i; i < len; ++i) {
            if (cfg.participants[i] == address(0)) revert InvalidConfig();
            if (i > 0 && uint160(cfg.participants[i]) <= uint160(cfg.participants[i - 1])) {
                revert ParticipantsNotSorted();
            }
            _participants.add(cfg.participants[i]);
        }
        participantCount = len;

        status = Status.FUNDING;
    }

    // ── Deposit ──────────────────────────────────────────────────────────

    /// @notice Deposit tokens for a participant. Caller must have approved this contract.
    ///         Auto-transitions FUNDING → ACTIVE when last deposit lands.
    function deposit(address participant) external nonReentrant onlyStatus(Status.FUNDING) {
        if (block.timestamp > fundingDeadline) revert FundingDeadlinePassed();
        _requireParticipant(participant);
        if (hasDeposited[participant]) revert AlreadyDeposited(participant);

        uint256 balBefore = SafeTransferLib.balanceOf(token, address(this));
        SafeTransferLib.safeTransferFrom(token, msg.sender, address(this), depositAmount);
        uint256 balAfter = SafeTransferLib.balanceOf(token, address(this));
        if (balAfter - balBefore != depositAmount) {
            revert DepositTransferMismatch(depositAmount, balAfter - balBefore);
        }

        _recordDeposit(participant);
    }

    /// @notice Factory-only: records deposit when factory already transferred tokens.
    function recordDeposit(address participant) external onlyFactory onlyStatus(Status.FUNDING) {
        if (block.timestamp > fundingDeadline) revert FundingDeadlinePassed();
        _requireParticipant(participant);
        if (hasDeposited[participant]) revert AlreadyDeposited(participant);
        _recordDeposit(participant);
    }

    /// @notice Deposit via Permit2 signature transfer. No prior ERC-20 approval needed
    ///         (only Permit2 allowance, which MONTE grants natively).
    /// @param participant The participant whose deposit slot to fill.
    /// @param permit Permit2 transfer parameters (token, amount, nonce, deadline).
    /// @param owner The token owner who signed the Permit2 message.
    /// @param signature The EIP-712 signature over the Permit2 transfer.
    function depositWithPermit2(
        address participant,
        ISignatureTransfer.PermitTransferFrom calldata permit,
        address owner,
        bytes calldata signature
    ) external nonReentrant onlyStatus(Status.FUNDING) {
        if (block.timestamp > fundingDeadline) revert FundingDeadlinePassed();
        _requireParticipant(participant);
        if (hasDeposited[participant]) revert AlreadyDeposited(participant);

        uint256 balBefore = SafeTransferLib.balanceOf(token, address(this));
        ISignatureTransfer(PERMIT2).permitTransferFrom(
            permit,
            ISignatureTransfer.SignatureTransferDetails({ to: address(this), requestedAmount: depositAmount }),
            owner,
            signature
        );
        uint256 balAfter = SafeTransferLib.balanceOf(token, address(this));
        if (balAfter - balBefore != depositAmount) {
            revert DepositTransferMismatch(depositAmount, balAfter - balBefore);
        }

        _recordDeposit(participant);
    }

    function _recordDeposit(address participant) private {
        hasDeposited[participant] = true;
        uint256 newCount = ++depositCount;
        emit Deposited(participant, depositAmount);

        if (newCount == participantCount) {
            emit StatusChanged(Status.FUNDING, Status.ACTIVE);
            status = Status.ACTIVE;
        }
    }

    // ── Settle ───────────────────────────────────────────────────────────

    /// @notice Submit admin-signed settlement. Distributes payouts minus rake.
    ///         `sum(payouts.amount)` must equal token balance of this contract.
    ///         Callable from FUNDING or ACTIVE state.
    function settle(Payout[] calldata payouts, bytes calldata signature)
        external
        nonReentrant
    {
        if (status != Status.FUNDING && status != Status.ACTIVE) {
            revert InvalidStatus(status, Status.ACTIVE);
        }
        if (payouts.length == 0) revert InvalidConfig();

        // Verify EIP-712 signature
        bytes32 structHash = _hashSettlement(payouts);
        bytes32 digest = _hashTypedData(structHash);
        address signer = ECDSA.recoverCalldata(digest, signature);
        if (signer != admin) revert InvalidSignature();

        uint256 balance = SafeTransferLib.balanceOf(token, address(this));

        // Verify payouts sum to balance and recipients are participants
        uint256 payoutSum;
        for (uint256 i; i < payouts.length; ++i) {
            _requireParticipant(payouts[i].recipient);
            payoutSum += payouts[i].amount;
        }
        if (payoutSum != balance) revert PayoutSumMismatch(balance, payoutSum);

        Status prev = status;
        status = Status.SETTLED;
        emit StatusChanged(prev, Status.SETTLED);

        uint256 totalRake = _distribute(payouts);
        emit Settled(payoutSum, totalRake);
    }

    // ── Expire ───────────────────────────────────────────────────────────

    /// @notice Transition to EXPIRED if past applicable deadline. Anyone can call.
    function expire() external {
        if (status == Status.FUNDING) {
            if (block.timestamp <= fundingDeadline) revert DeadlineNotPassed();
        } else if (status == Status.ACTIVE) {
            if (block.timestamp <= settlementDeadline) revert DeadlineNotPassed();
        } else {
            revert InvalidStatus(status, Status.FUNDING);
        }
        emit StatusChanged(status, Status.EXPIRED);
        status = Status.EXPIRED;
    }

    // ── Withdraw ─────────────────────────────────────────────────────────

    /// @notice EXPIRED only. Returns depositAmount to depositors. No rake.
    function withdraw() external nonReentrant onlyStatus(Status.EXPIRED) {
        if (!hasDeposited[msg.sender]) revert NotDepositor(msg.sender);
        hasDeposited[msg.sender] = false;
        SafeTransferLib.safeTransfer(token, msg.sender, depositAmount);
        emit Withdrawn(msg.sender, depositAmount);
    }

    // ── Claim Failed ─────────────────────────────────────────────────────

    /// @notice SETTLED only. Pull-based claim for failed push transfers.
    function claimFailed() external nonReentrant onlyStatus(Status.SETTLED) {
        uint256 amount = failedClaims[msg.sender];
        if (amount == 0) revert NoFailedClaim(msg.sender);
        failedClaims[msg.sender] = 0;
        SafeTransferLib.safeTransfer(token, msg.sender, amount);
        emit ClaimedFailed(msg.sender, amount);
    }

    // ── Views ────────────────────────────────────────────────────────────

    function getStatus() external view returns (Status) {
        return status;
    }

    function allDeposited() external view returns (bool) {
        return depositCount == participantCount;
    }

    function getParticipants() external view returns (address[] memory) {
        return _participants.values();
    }

    function isParticipant(address addr) external view returns (bool) {
        return _participants.contains(addr);
    }

    function getConfig() external view returns (
        address token_,
        address admin_,
        address rakeBeneficiary_,
        uint256 depositAmount_,
        uint16  rakeBps_,
        uint256 fundingDeadline_,
        uint256 settlementDeadline_,
        address[] memory participants_
    ) {
        return (
            token, admin, rakeBeneficiary,
            depositAmount, rakeBps,
            fundingDeadline, settlementDeadline,
            _participants.values()
        );
    }

    // ── Internal ─────────────────────────────────────────────────────────

    /// @dev Distributes payouts minus rake. Returns total rake collected.
    function _distribute(Payout[] calldata payouts) private returns (uint256 totalRake) {
        address tok = token;
        uint16 bps = rakeBps;
        for (uint256 i; i < payouts.length; ++i) {
            uint256 gross = payouts[i].amount;
            uint256 rake = (gross * bps) / MAX_BPS;
            uint256 net = gross - rake;
            totalRake += rake;

            if (net > 0) {
                address recipient = payouts[i].recipient;
                // Push with try/catch: use IERC20.transfer (not safeTransfer)
                // so failed transfers are stored for pull-based claim
                try IERC20(tok).transfer(recipient, net) returns (bool success) {
                    if (!success) {
                        failedClaims[recipient] += net;
                        emit FailedTransfer(recipient, net);
                    }
                } catch {
                    failedClaims[recipient] += net;
                    emit FailedTransfer(recipient, net);
                }
            }
        }

        // Rake to beneficiary (trusted address, revert on failure)
        if (totalRake > 0) {
            SafeTransferLib.safeTransfer(tok, rakeBeneficiary, totalRake);
        }
    }

    /// @dev O(1) participant check via EnumerableSetLib.
    function _requireParticipant(address addr) private view {
        if (!_participants.contains(addr)) revert NotParticipant(addr);
    }

    function _domainSeparator() private view returns (bytes32) {
        return keccak256(
            abi.encode(DOMAIN_TYPEHASH, NAME_HASH, VERSION_HASH, block.chainid, address(this))
        );
    }

    function _hashTypedData(bytes32 structHash) private view returns (bytes32) {
        return keccak256(abi.encodePacked("\x19\x01", _domainSeparator(), structHash));
    }

    function _hashSettlement(Payout[] calldata payouts) private pure returns (bytes32) {
        bytes32[] memory payoutHashes = new bytes32[](payouts.length);
        for (uint256 i; i < payouts.length; ++i) {
            payoutHashes[i] = keccak256(
                abi.encode(PAYOUT_TYPEHASH, payouts[i].recipient, payouts[i].amount)
            );
        }
        return keccak256(
            abi.encode(SETTLE_TYPEHASH, keccak256(abi.encodePacked(payoutHashes)))
        );
    }
}
