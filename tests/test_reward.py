from ape import chain
import pytest
from utils.constants import MAX_INT, ROLES


def test_rewards_selling(
    asset,
    ctoken,
    user,
    create_vault_and_strategy,
    gov,
    strategist,
    amount,
    provide_strategy_with_debt,
    comp,
    comp_whale,
):
    vault, strategy = create_vault_and_strategy(gov, amount)
    new_debt = amount
    provide_strategy_with_debt(gov, strategy, vault, new_debt)

    before_bal = strategy.totalAssets()

    reward = 11 * 10 ** comp.decimals()
    comp.transfer(strategy, reward, sender=comp_whale)
    assert comp.balanceOf(strategy) == reward

    # Set uni fees
    strategy.setUniFees(3000, 500, sender=strategist)

    # tend function should still work and will swap rewards any rewards
    strategy.tend(sender=vault)

    # rewards should be sold
    assert strategy.totalAssets() > before_bal
    assert comp.balanceOf(strategy) == 0


def test_rewards_apr(strategy, asset):
    # get apr in percentage (100 / 1e18)
    apr = strategy.getRewardAprForSupplyBase(0) / 1e16
    # for current apr visit compound website: https://v2-app.compound.finance/
    assert apr < 1  # all rewards are less than 1%
    assert apr > 0.1  # all rewards are higher than 0.1%
    # supplying more capital should reward in smaller rewards
    assert strategy.getRewardAprForSupplyBase(0) > strategy.getRewardAprForSupplyBase(
        1000 * 10 ** asset.decimals()
    )


def test_rewards_pending(
    asset,
    ctoken,
    user,
    create_vault_and_strategy,
    gov,
    strategist,
    amount,
    provide_strategy_with_debt,
    comp,
    asset_whale,
):
    vault, strategy = create_vault_and_strategy(gov, amount)
    new_debt = amount
    provide_strategy_with_debt(gov, strategy, vault, new_debt)

    # Take some time for rewards to accrue
    chain.mine(3600 * 24 * 10)

    # Somebody deposits to trigger rewards calculation
    ctoken.mint(amount, sender=asset_whale)

    # rewards should be pending buy not claimed
    rewards_pending = strategy.getRewardsPending()
    assert rewards_pending > 0
    assert comp.balanceOf(strategy) == 0

    # Don't sell rewards but claim all
    strategy.setRewardStuff(MAX_INT, 1, sender=strategist)

    # tend function should still work and will not swap any rewards
    strategy.tend(sender=vault)

    assert comp.balanceOf(strategy) >= rewards_pending
    assert comp.balanceOf(strategy) < rewards_pending * 1.1
