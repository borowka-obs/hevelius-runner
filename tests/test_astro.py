from astro import dec_to_sexagesimal, ra_to_sexagesimal


def test_ra_to_sexagesimal_formats_hms():
    assert ra_to_sexagesimal(12.5) == "12 30 00"


def test_dec_to_sexagesimal_positive_value():
    assert dec_to_sexagesimal(12.5) == "12 30 00"


def test_dec_to_sexagesimal_negative_value():
    assert dec_to_sexagesimal(-12.5) == "-12 30 00"
