"""Ground-proof label classification: combined labels split, buckets rejected honestly.

Covers the pure mapping tables in the transcript connector (no DB): every combined
label must name ONLY specific registry commodities, and generic/non-produce labels
must get explicit reject reasons instead of a bare "unresolved".
"""

from vervana.connectors.transcript import _combined_components, _unresolved_reason


def test_combined_labels_map_to_specific_components():
    assert _combined_components("Tomato + Peas") == ("Tomato", "Green Peas")
    assert _combined_components("Chilli + Capsicum") == ("Green Chilli", "Capsicum")
    assert _combined_components("Apple + Capsicum") == ("Apple", "Capsicum")
    assert _combined_components("Mosambi + Guava") == ("Mosambi", "Guava")


def test_combined_matching_is_case_and_space_tolerant():
    assert _combined_components(" tomato   +  PEAS ") == ("Tomato", "Green Peas")


def test_single_and_unknown_labels_do_not_split():
    assert _combined_components("Onion") is None
    assert _combined_components("Mango + Fruits (all)") is None


def test_generic_buckets_get_explicit_reasons():
    assert _unresolved_reason("Fruits (all)") == "generic_bucket_label"
    assert _unresolved_reason("Vegetables (all)") == "generic_bucket_label"
    assert (
        _unresolved_reason("Fruits (all) + Vegetables (all)") == "generic_bucket_label"
    )
    assert _unresolved_reason("Other") == "generic_bucket_label"


def test_combined_with_generic_bucket_gets_explicit_reason():
    assert _unresolved_reason("Mango + Fruits (all)") == "combined_with_generic_bucket"
    assert _unresolved_reason("Orange + Fruits (all)") == "combined_with_generic_bucket"


def test_non_produce_label_gets_explicit_reason():
    assert _unresolved_reason("Gold & Silver") == "non_produce_label"


def test_unknown_labels_stay_unresolved():
    assert _unresolved_reason("Dragon Fruit") == "unresolved_commodity"
