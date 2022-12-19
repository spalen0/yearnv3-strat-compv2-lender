from ape import reverts
import pytest
from utils.constants import REL_ERROR, MAX_INT, BLOCKS_PER_YEAR, ROLES


def test_strategy_constructor(asset, vault, strategy):
    assert strategy.name() == "strategy_name"
    assert strategy.asset() == asset.address
    assert strategy.vault() == vault.address


def test_max_deposit(strategy, vault):
    assert strategy.maxDeposit(vault) == MAX_INT


@pytest.mark.parametrize("shares_amount", [10**6, 10**8, 10**12, 10**18])
def test_convert_to_assets(strategy, shares_amount):
    assert shares_amount == strategy.convertToAssets(shares_amount)


# @pytest.mark.parametrize("shares_amount", [10**6, 10**8, 10**12, 10**18])
# def test_convert_to_assets_with_supply(
#     asset,
#     create_vault_and_strategy,
#     gov,
#     amount,
#     shares_amount,
#     provide_strategy_with_debt,
# ):
#     vault, strategy = create_vault_and_strategy(gov, amount)
#     assert strategy.totalAssets() == 0
#
#     # let's provide strategy with assets
#     new_debt = amount // 2
#     provide_strategy_with_debt(gov, strategy, vault, new_debt)
#
#     assert strategy.convertToAssets(shares_amount) == shares_amount
#
#     # let´s change pps by transferring (not deposit) assets to strategy
#     asset.transfer(strategy, new_debt, sender=vault)
#
#     assert asset.balanceOf(strategy) == new_debt
#     assert strategy.convertToAssets(shares_amount) == pytest.approx(
#         2 * shares_amount, rel=REL_ERROR
#     )


@pytest.mark.parametrize("assets_amount", [10**6, 10**8, 10**12, 10**18])
def test_convert_to_shares(strategy, assets_amount):
    assert assets_amount == strategy.convertToShares(assets_amount)


# @pytest.mark.parametrize("assets_amount", [10**6, 10**8, 10**12, 10**18])
# def test_convert_to_shares_with_supply(
#     asset,
#     create_vault_and_strategy,
#     gov,
#     amount,
#     assets_amount,
#     provide_strategy_with_debt,
# ):
#     vault, strategy = create_vault_and_strategy(gov, amount)
#     assert strategy.totalAssets() == 0
#
#     # let's provide strategy with assets
#     new_debt = amount // 2
#     provide_strategy_with_debt(gov, strategy, vault, new_debt)
#
#     # pps == 1.0
#     assert strategy.convertToShares(assets_amount) == assets_amount
#
#     # let´s change pps by transferring (not deposit) assets to strategy
#     asset.transfer(strategy, new_debt, sender=vault)
#
#     assert asset.balanceOf(strategy) == new_debt
#     assert strategy.convertToShares(assets_amount) == pytest.approx(
#         assets_amount / 2, rel=REL_ERROR
#     )


def test_total_assets(
    gov, asset, ctoken, create_vault_and_strategy, provide_strategy_with_debt, amount
):
    vault, strategy = create_vault_and_strategy(gov, amount)
    assert strategy.totalAssets() == 0

    # let's provide strategy with assets
    new_debt = amount
    provide_strategy_with_debt(gov, strategy, vault, new_debt)

    assert pytest.approx(new_debt, REL_ERROR) == strategy.totalAssets()
    assert asset.balanceOf(vault) == amount - new_debt
    assert asset.balanceOf(strategy) == 0
    assert pytest.approx(new_debt, REL_ERROR) == strategy.balanceOfCToken()


def test_balance_of(create_vault_and_strategy, gov, amount, provide_strategy_with_debt):
    vault, strategy = create_vault_and_strategy(gov, amount)
    assert strategy.totalAssets() == 0

    new_debt = amount // 2
    provide_strategy_with_debt(gov, strategy, vault, new_debt)

    assert pytest.approx(strategy.balanceOf(vault), 1e-4) == new_debt

    new_new_debt = amount // 4
    provide_strategy_with_debt(gov, strategy, vault, new_debt + new_new_debt)

    assert pytest.approx(new_debt + new_new_debt, 1e-4) == strategy.balanceOf(vault)


def test_deposit_no_vault__reverts(create_vault_and_strategy, gov, amount, user):
    vault, strategy = create_vault_and_strategy(gov, amount)
    with reverts("not vault"):
        strategy.deposit(100, user, sender=user)

    # will revert due to no approval
    with reverts():
        strategy.deposit(100, user, sender=vault)


def test_deposit(
    asset, ctoken, create_vault_and_strategy, gov, amount, provide_strategy_with_debt
):
    vault, strategy = create_vault_and_strategy(gov, amount)
    assert strategy.totalAssets() == 0

    new_debt = amount // 2
    provide_strategy_with_debt(gov, strategy, vault, new_debt)

    assert pytest.approx(strategy.balanceOf(vault), 1e-5) == new_debt

    assert asset.balanceOf(vault) == amount // 2
    # get's reinvested directly
    assert asset.balanceOf(strategy) == 0
    assert pytest.approx(new_debt, REL_ERROR) == strategy.balanceOfCToken()


def test_max_withdraw(
    asset, ctoken, create_vault_and_strategy, gov, amount, provide_strategy_with_debt
):
    vault, strategy = create_vault_and_strategy(gov, amount)
    assert strategy.maxWithdraw(vault) == 0

    new_debt = amount // 2
    provide_strategy_with_debt(gov, strategy, vault, new_debt)

    assert pytest.approx(new_debt, REL_ERROR) == strategy.maxWithdraw(vault)


def test_max_withdraw_no_liquidity(
    asset,
    ctoken,
    user,
    create_vault_and_strategy,
    gov,
    amount,
    provide_strategy_with_debt,
):
    vault, strategy = create_vault_and_strategy(gov, amount)
    assert strategy.maxWithdraw(vault) == 0

    new_debt = amount // 2
    provide_strategy_with_debt(gov, strategy, vault, new_debt)

    assert pytest.approx(new_debt, REL_ERROR) == strategy.maxWithdraw(vault)

    # let's drain ctoken contract
    asset.transfer(
        user, asset.balanceOf(ctoken) - 10 ** vault.decimals(), sender=ctoken
    )

    assert strategy.maxWithdraw(vault) == strategy.totalAssets()


def test_withdraw_above_max__reverts(create_vault_and_strategy, gov, amount, user):
    vault, strategy = create_vault_and_strategy(gov, amount)
    with reverts("withdraw more than max"):
        strategy.withdraw(100, vault, vault, sender=vault)


def test_withdraw_more_than_max(
    asset, ctoken, create_vault_and_strategy, gov, amount, provide_strategy_with_debt
):
    vault, strategy = create_vault_and_strategy(gov, amount)
    new_debt = amount // 2
    provide_strategy_with_debt(gov, strategy, vault, new_debt)

    with reverts("withdraw more than max"):
        strategy.withdraw(
            strategy.maxWithdraw(vault) + 10 ** vault.decimals(),
            vault,
            vault,
            sender=vault,
        )


def test_withdraw(
    asset, ctoken, create_vault_and_strategy, gov, amount, provide_strategy_with_debt
):
    vault, strategy = create_vault_and_strategy(gov, amount)
    new_debt = amount // 2
    provide_strategy_with_debt(gov, strategy, vault, new_debt)

    assert asset.balanceOf(strategy) == 0
    assert asset.balanceOf(vault) == amount // 2
    assert pytest.approx(new_debt, REL_ERROR) == strategy.balanceOfCToken()

    strategy.withdraw(strategy.maxWithdraw(vault), vault, vault, sender=vault)

    assert pytest.approx(0, abs=1e4) == strategy.balanceOf(vault)
    assert asset.balanceOf(strategy) == 0
    assert pytest.approx(amount, REL_ERROR) == asset.balanceOf(vault)
    assert pytest.approx(0, abs=1e4) == strategy.balanceOfCToken()


def test_withdraw_low_liquidity(
    asset,
    ctoken,
    user,
    create_vault_and_strategy,
    gov,
    amount,
    provide_strategy_with_debt,
):
    vault, strategy = create_vault_and_strategy(gov, amount)
    new_debt = amount
    provide_strategy_with_debt(gov, strategy, vault, new_debt)

    assert asset.balanceOf(strategy) == 0
    assert asset.balanceOf(vault) == 0
    assert pytest.approx(new_debt, REL_ERROR) == strategy.balanceOfCToken()

    # let's drain ctoken contract
    tx_drain = asset.transfer(
        user, asset.balanceOf(ctoken) - 10 ** vault.decimals(), sender=ctoken
    )
    # cToken exchangeRateStored has changed without cash(asset):
    # exchangeRate = (getCash() + totalBorrows() - totalReserves()) / totalSupply()
    assert new_debt - 10 ** vault.decimals() > strategy.balanceOfCToken()

    max_withdraw = strategy.maxWithdraw(vault)
    assert max_withdraw == strategy.totalAssets()
    tx = strategy.withdraw(max_withdraw, vault, vault, sender=vault)

    # all is in cToken because underlying asset is drained
    assert strategy.balanceOf(vault) == strategy.balanceOfCToken()
    assert asset.balanceOf(strategy) == 0
    assert pytest.approx(10 ** vault.decimals(), REL_ERROR) == asset.balanceOf(vault)
    # cToken is worth less because of drained cash
    assert new_debt - max_withdraw > strategy.balanceOfCToken()


def test_apr(
    asset,
    ctoken,
    user,
    create_vault_and_strategy,
    gov,
    amount,
    provide_strategy_with_debt,
    comp,
    comptroller,
    price_feed,
):
    vault, strategy = create_vault_and_strategy(gov, amount)
    new_debt = amount
    provide_strategy_with_debt(gov, strategy, vault, new_debt)

    asset_decimals = vault.decimals()
    comp_speed = comptroller.compSupplySpeeds(strategy.cToken()) * BLOCKS_PER_YEAR
    comp_price = price_feed.price("COMP")
    asset_price = price_feed.getUnderlyingPrice(strategy.cToken()) / 10 ** (
        30 - asset_decimals
    )
    ctoken_total_supply_in_want = (
        ctoken.totalSupply() * ctoken.exchangeRateStored() / 1e18
    )
    rewards_apr = (
        comp_speed
        * comp_price
        * 10**asset_decimals
        / (ctoken_total_supply_in_want * asset_price)
    )

    current_real_apr = ctoken.supplyRatePerBlock() * BLOCKS_PER_YEAR
    current_expected_apr_with_rewards = strategy.aprAfterDebtChange(0)
    assert (
        pytest.approx(current_real_apr + rewards_apr, rel=1e-5)
        == current_expected_apr_with_rewards
    )
    assert pytest.approx(rewards_apr, rel=1e-5) == strategy.getRewardAprForSupplyBase(0)

    # TODO: is there a way to re calculate without replicating in python?
    assert current_real_apr + rewards_apr < strategy.aprAfterDebtChange(-int(1e12))
    assert current_real_apr + rewards_apr > strategy.aprAfterDebtChange(int(1e12))


def test_tend(
    asset,
    ctoken,
    user,
    create_vault_and_strategy,
    gov,
    strategist,
    amount,
    provide_strategy_with_debt,
):
    vault, strategy = create_vault_and_strategy(gov, amount)
    new_debt = amount
    provide_strategy_with_debt(gov, strategy, vault, new_debt)

    before_bal = strategy.totalAssets()

    # set gov to keeper role
    vault.set_role(gov.address, ROLES.KEEPER, sender=gov)

    # tend function should still work and not revert without any rewards
    vault.tend_strategy(strategy.address, sender=gov)

    stored_balance = strategy.balanceOfCToken()
    # this will trigger to recalculating the exchange rate used for cToken
    calculated_balance = ctoken.balanceOfUnderlying(
        strategy, sender=strategist
    ).return_value
    assert calculated_balance > stored_balance

    # no rewards should be claimed but the call accrues the account so we should be slightly higher
    assert strategy.totalAssets() > before_bal
