// SPDX-License-Identifier: AGPL-3.0
pragma solidity 0.8.14;

import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/math/Math.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

import {IERC20, BaseStrategy} from "BaseStrategy.sol";
import "./interfaces/IVault.sol";
import "./interfaces/ISwapRouter.sol";
import "./interfaces/ITradeFactory.sol";
import "./interfaces/comp/CErc20I.sol";
import "./interfaces/comp/InterestRateModel.sol";
import "./interfaces/comp/ComptrollerI.sol";
import "./interfaces/comp/UniswapAnchoredViewI.sol";

contract Strategy is BaseStrategy, Ownable {
    using SafeERC20 for IERC20;

    //Uniswap v3 router
    ISwapRouter internal constant UNISWAP_ROUTER =
        ISwapRouter(0xE592427A0AEce92De3Edee1F18E0157C05861564);
    //Fees for the V3 pools if the supply is incentivized
    uint24 public compToEthFee;
    uint24 public ethToWantFee;

    // eth blocks are mined every 12s -> 3600 * 24 * 365 / 12 = 2_628_000
    uint256 private constant BLOCKS_PER_YEAR = 2_628_000;
    address public constant COMP =
        address(0xc00e94Cb662C3520282E6f5717214004A7f26888);
    address public constant WETH =
        address(0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2);
    ComptrollerI public constant COMPTROLLER =
        ComptrollerI(0x3d9819210A31b4961b30EF54bE2aeD79B9c9Cd3B);
    UniswapAnchoredViewI public constant PRICE_FEED =
        UniswapAnchoredViewI(0x65c816077C29b557BEE980ae3cC2dCE80204A0C5);

    uint256 public minCompToSell = 1 ether;
    uint256 public minCompToClaim = 1 ether;
    uint256 public dustThreshold = 1;
    address public tradeFactory;

    CErc20I public immutable cToken;

    constructor(
        address _vault,
        string memory _name,
        CErc20I _cToken
    ) BaseStrategy(_vault, _name) {
        cToken = _cToken;
        require(cToken.underlying() == IVault(vault).asset(), "WRONG CTOKEN");
        IERC20(IVault(vault).asset()).safeApprove(
            address(_cToken),
            type(uint256).max
        );
        IERC20(COMP).safeApprove(address(UNISWAP_ROUTER), type(uint256).max);
    }

    function _maxWithdraw(
        address owner
    ) internal view override returns (uint256) {
        // TODO: may not be accurate due to unaccrued balance in cToken
        return
            Math.min(IERC20(asset).balanceOf(address(cToken)), _totalAssets());
    }

    function _freeFunds(
        uint256 _amount
    ) internal returns (uint256 _amountFreed) {
        uint256 idleAmount = balanceOfAsset();
        if (_amount <= idleAmount) {
            // we have enough idle assets for the vault to take
            _amountFreed = _amount;
        } else {
            // NOTE: we need the balance updated
            // balanceOfUnderlying accrues interest in a transaction
            uint256 balanceUnderlying = cToken.balanceOfUnderlying(
                address(this)
            );
            // We need to take from Compound enough to reach _amount
            // We run with 'unchecked' as we are safe from underflow
            unchecked {
                _withdrawFromCompound(
                    Math.min(_amount - idleAmount, balanceUnderlying)
                );
            }
            _amountFreed = balanceOfAsset();
        }
    }

    function _withdraw(
        uint256 amount,
        address receiver,
        address owner
    ) internal override returns (uint256) {
        return _freeFunds(amount);
    }

    function _totalAssets() internal view override returns (uint256) {
        return balanceOfAsset() + balanceOfCToken();
    }

    function _invest() internal override {
        uint256 _availableToInvest = balanceOfAsset();
        if (_availableToInvest > 0) {
            _depositToCompound(_availableToInvest);
        }
    }

    function _withdrawFromCompound(uint256 _amount) internal {
        if (_amount > dustThreshold) {
            require(
                cToken.redeemUnderlying(_amount) == 0,
                "cToken: redeemUnderlying fail"
            );
        }
    }

    function _depositToCompound(uint256 _amount) internal {
        require(cToken.mint(_amount) == 0, "cToken: mint fail");
    }

    function balanceOfCToken() public view returns (uint256) {
        uint256 balance = cToken.balanceOf(address(this));
        if (balance == 0) {
            return 0;
        } else {
            //The current exchange rate as an unsigned integer, scaled by 1e18.
            return (balance * cToken.exchangeRateStored()) / 1e18;
        }
    }

    function balanceOfAsset() public view returns (uint256) {
        return IERC20(asset).balanceOf(address(this));
    }

    function aprAfterDebtChange(int256 delta) external view returns (uint256) {
        uint256 cashPrior = cToken.getCash();
        uint256 borrows = cToken.totalBorrows();
        uint256 reserves = cToken.totalReserves();
        uint256 reserverFactor = cToken.reserveFactorMantissa();
        InterestRateModel model = cToken.interestRateModel();

        //the supply rate is derived from the borrow rate, reserve factor and the amount of total borrows.
        uint256 supplyRate = model.getSupplyRate(
            uint256(int256(cashPrior) + delta),
            borrows,
            reserves,
            reserverFactor
        );
        uint256 newSupply = supplyRate * BLOCKS_PER_YEAR;
        uint256 rewardApr = getRewardAprForSupplyBase(delta);
        return newSupply + rewardApr;
    }

    /**
     * @notice Get the current reward for supplying APR in Compound
     * @param newAmount Any amount that will be added to the total supply in a deposit
     * @return The reward APR calculated by converting tokens value to USD with a decimal scaled up by 1e18
     */
    function getRewardAprForSupplyBase(
        int256 newAmount
    ) public view returns (uint256) {
        // COMP issued per block to suppliers * (1 * 10 ^ 18)
        uint256 compSpeedPerBlock = COMPTROLLER.compSupplySpeeds(
            address(cToken)
        );
        if (compSpeedPerBlock == 0) {
            return 0;
        }
        // Approximate COMP issued per year to suppliers * (1 * 10 ^ 18)
        uint256 compSpeedPerYear = compSpeedPerBlock * BLOCKS_PER_YEAR;

        // The price of the asset in USD as an unsigned integer scaled up by 10 ^ 6
        uint256 rewardTokenPriceInUsd = PRICE_FEED.price("COMP");

        uint256 assetDecimals = IVault(vault).decimals();

        // https://docs.compound.finance/v2/prices/#underlying-price
        // The price of the asset in USD as an unsigned integer scaled up by 10 ^ (36 - underlying asset decimals)
        // upscale to price COMP percision 10 ^ 6
        uint256 wantPriceInUsd = PRICE_FEED.getUnderlyingPrice(
            address(cToken)
        ) / 10 ** (30 - assetDecimals);

        uint256 cTokenTotalSupplyInWant = (cToken.totalSupply() *
            cToken.exchangeRateStored()) / 1e18;
        uint256 wantTotalSupply = uint256(
            int256(cTokenTotalSupplyInWant) + newAmount
        );

        return
            (compSpeedPerYear * rewardTokenPriceInUsd * 10 ** assetDecimals) /
            (wantTotalSupply * wantPriceInUsd);
    }

    /**
     * @notice Get pending COMP rewards for supplying want token
     * @dev Pending rewards are update in comptroller afer every ctoken mint or redeem
     * @return Amount of pending COMP tokens
     */
    function getRewardsPending() public view returns (uint256) {
        // https://github.com/compound-finance/compound-protocol/blob/master/contracts/Comptroller.sol#L1230
        ComptrollerI.CompMarketState memory supplyState = COMPTROLLER
            .compSupplyState(address(cToken));
        uint256 supplyIndex = supplyState.index;
        uint256 supplierIndex = COMPTROLLER.compSupplierIndex(
            address(cToken),
            address(this)
        );

        // Calculate change in the cumulative sum of the COMP per cToken accrued
        uint256 deltaIndex = supplyIndex - supplierIndex;

        // Calculate COMP accrued: cTokenAmount * accruedPerCToken / doubleScale
        return (cToken.balanceOf(address(this)) * deltaIndex) / 1e36;
    }

    function harvest() external onlyOwner {
        if (getRewardsPending() > minCompToClaim) {
            _claimRewards();
        }

        if (tradeFactory == address(0) && compToEthFee != 0) {
            _disposeOfComp();
        }

        _invest();
    }

    /*
     * External function that Claims the reward tokens due to this contract address
     */
    function claimRewards() external onlyOwner {
        _claimRewards();
    }

    /*
     * Claims the reward tokens due to this contract address
     */
    function _claimRewards() internal {
        CTokenI[] memory cTokens = new CTokenI[](1);
        cTokens[0] = cToken;
        address[] memory holders = new address[](1);
        holders[0] = address(this);
        COMPTROLLER.claimComp(holders, cTokens, false, true);
    }

    function _disposeOfComp() internal {
        uint256 compBalance = IERC20(COMP).balanceOf(address(this));

        if (compBalance > minCompToSell) {
            bytes memory path = abi.encodePacked(
                COMP, // comp-ETH
                compToEthFee,
                WETH, // ETH-want
                ethToWantFee,
                IVault(vault).asset()
            );

            // Proceeds from Comp are not subject to minExpectedSwapPercentage
            // so they could get sandwiched if we end up in an uncle block
            UNISWAP_ROUTER.exactInput(
                ISwapRouter.ExactInputParams(
                    path,
                    address(this),
                    block.timestamp,
                    compBalance,
                    0
                )
            );
        }
    }

    //These will default to 0.
    //Will need to be manually set if want is incentized before any harvests
    function setUniFees(
        uint24 _compToEth,
        uint24 _ethToWant
    ) external onlyOwner {
        compToEthFee = _compToEth;
        ethToWantFee = _ethToWant;
    }

    /**
     * @notice Set values for handling COMP reward token
     * @param _minCompToSell Minimum value that will be sold
     * @param _minCompToClaim Minimum vaule to claim from compound
     */
    function setRewardStuff(
        uint256 _minCompToSell,
        uint256 _minCompToClaim
    ) external onlyOwner {
        minCompToSell = _minCompToSell;
        minCompToClaim = _minCompToClaim;
    }

    /**
     * @notice Set minimal value that can be withdraw from compound
     * @dev This is need because cToken and underlying don't have the same value and
     * for too low values the rounding will be 0 which will cause comptroller revert: redeemTokens zero.
     * Minimal values: USDT/USDC = 1, DAI/other=1e9
     * @param _dustThreshold Minimum value to withdraw from compound
     */
    function setDustThreshold(uint256 _dustThreshold) external onlyOwner {
        dustThreshold = _dustThreshold;
    }

    // ---------------------- YSWAPS FUNCTIONS ----------------------
    function setTradeFactory(address _tradeFactory) external onlyOwner {
        if (tradeFactory != address(0)) {
            _removeTradeFactoryPermissions();
        }

        ITradeFactory tf = ITradeFactory(_tradeFactory);

        IERC20(COMP).safeApprove(_tradeFactory, type(uint256).max);
        tf.enable(COMP, IVault(vault).asset());

        tradeFactory = _tradeFactory;
    }

    function removeTradeFactoryPermissions() external onlyOwner {
        _removeTradeFactoryPermissions();
    }

    function _removeTradeFactoryPermissions() internal {
        IERC20(COMP).safeApprove(tradeFactory, 0);

        tradeFactory = address(0);
    }
}
