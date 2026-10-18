from espresso_mod.services.peak import PeakPressure


def test_the_peak_keeps_the_highest_reading():
    peak = PeakPressure()
    assert peak.bar is None

    peak.observe(3.0)
    peak.observe(9.4)
    peak.observe(7.0)

    assert peak.bar == 9.4


def test_reset_forgets_the_previous_shot():
    peak = PeakPressure()
    peak.observe(8.0)

    peak.reset()

    assert peak.bar is None
