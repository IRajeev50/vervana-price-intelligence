"""The Book cost stack: integer paise, visible rates, honest missing-logistics (M17).

No network. Rates come from the committed book_costs.csv; costs are exact paise.
"""

from __future__ import annotations

from vervana.book.costs import (
    carrying_cost,
    load_cost_rates,
    logistics_cost,
    sell_now_cost,
)


def test_rates_fall_back_to_default_row_for_unlisted_commodity():
    rates = load_cost_rates("Dragonfruit")  # not in the CSV
    assert rates.key == "__default__"
    assert rates.storage_paise_per_kg_per_day == 5


def test_listed_commodity_uses_its_own_row():
    rates = load_cost_rates("Tomato")
    assert rates.key == "Tomato"
    assert rates.spoilage_pct_per_day == 2.0  # tomato spoils fast


def test_carrying_cost_is_integer_paise_and_sums_components():
    rates = load_cost_rates("Potato")
    cb = carrying_cost(
        rates=rates,
        purchase_price_paise_per_kg=2000,  # ₹20/kg
        expected_sale_price_paise_per_kg=2500,  # ₹25/kg
        days=30,
        outbound_paise_per_kg=120,
    )
    assert isinstance(cb.total_paise_per_kg, int)
    # storage 4p × 30 = 120; financing 12%/yr on 2000 × 30/365 = round(19.7)=20;
    # logistics 120; quality 0.25%/day × 30 = 7.5% of 2500 = round(187.5)=188 (half-even)
    assert cb.storage.paise_per_kg == 120
    assert cb.financing.paise_per_kg == 20
    assert cb.logistics.paise_per_kg == 120
    assert cb.quality_loss.paise_per_kg == 188
    assert cb.total_paise_per_kg == 120 + 20 + 120 + 188


def test_missing_distance_is_zero_logistics_but_labelled_not_hidden():
    line = logistics_cost(None)
    assert line.paise_per_kg == 0
    assert "distance unknown" in line.basis


def test_sell_now_has_only_logistics():
    cb = sell_now_cost(90)
    assert cb.storage.paise_per_kg == 0
    assert cb.financing.paise_per_kg == 0
    assert cb.quality_loss.paise_per_kg == 0
    assert cb.logistics.paise_per_kg == 90
    assert cb.total_paise_per_kg == 90


def test_every_cost_line_shows_its_basis():
    rates = load_cost_rates("Onion")
    cb = carrying_cost(
        rates=rates,
        purchase_price_paise_per_kg=1500,
        expected_sale_price_paise_per_kg=1800,
        days=10,
        outbound_paise_per_kg=None,
    )
    for line in (cb.storage, cb.financing, cb.logistics, cb.quality_loss):
        assert line.basis  # never a bare number
