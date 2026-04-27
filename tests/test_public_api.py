import refua_schema as rs


def test_public_api_exposes_hierarchy() -> None:
    assert hasattr(rs, "Portfolio")
    assert hasattr(rs, "Disease")
    assert hasattr(rs, "Rationale")
    assert hasattr(rs, "Drug")
    assert hasattr(rs, "ClinicalTrial")


def test_public_api_exposes_io_helpers() -> None:
    assert hasattr(rs, "portfolio_to_mapping")
    assert hasattr(rs, "portfolio_from_mapping")
    assert hasattr(rs, "load_portfolio")
    assert hasattr(rs, "dump_portfolio")
