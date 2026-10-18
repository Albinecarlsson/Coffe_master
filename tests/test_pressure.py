from __future__ import annotations

import pytest

from espresso_mod.domain.pressure import PressureTransducer
from espresso_mod.hal.pressure_ads1115 import Ads1115Pressure

# ---- transducer maths ----


def test_transducer_maps_the_senders_span():
    transducer = PressureTransducer()

    # the ADC sees half the sender voltage: 0.25 V at 0 bar, 2.25 V at 16 bar
    assert transducer.bar(0.25) == pytest.approx(0.0)
    assert transducer.bar(1.25) == pytest.approx(8.0)
    assert transducer.bar(2.25) == pytest.approx(16.0)


def test_transducer_can_skip_the_divider():
    transducer = PressureTransducer(divider=1.0)

    assert transducer.bar(0.5) == pytest.approx(0.0)
    assert transducer.bar(2.5) == pytest.approx(8.0)


def test_transducer_clamps_outside_its_span():
    transducer = PressureTransducer()

    assert transducer.bar(0.0) == 0.0
    assert transducer.bar(5.0) == 16.0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"bar_max": 0.0},
        {"bar_max": -16.0},
        {"volts_min": 4.5, "volts_max": 0.5},
        {"divider": 0.0},
    ],
)
def test_transducer_rejects_a_nonsense_configuration(kwargs):
    with pytest.raises(ValueError):
        PressureTransducer(**kwargs)


# ---- ADS1115 driver ----


class FakeI2C:
    def __init__(self, raw: int = 0) -> None:
        self.raw = raw
        self.payload: list[int] | None = None
        self.fail_with: OSError | None = None
        self.writes: list[tuple[int, int, list[int]]] = []
        self.closed = False

    def write_i2c_block_data(self, address: int, register: int, data: list[int]) -> None:
        self.writes.append((address, register, list(data)))

    def read_i2c_block_data(self, address: int, register: int, length: int) -> list[int]:
        if self.fail_with is not None:
            raise self.fail_with
        if self.payload is not None:
            return self.payload
        return list(self.raw.to_bytes(2, "big", signed=True))

    def close(self) -> None:
        self.closed = True


def _raw(adc_volts: float, pga_volts: float = 4.096) -> int:
    return round(adc_volts * 32768.0 / pga_volts)


def _sensor(bus: FakeI2C, clock, **kwargs) -> Ads1115Pressure:
    sensor = Ads1115Pressure(bus, clock=clock, **kwargs)
    clock.sleep(0.05)  # past the warm-up window
    return sensor


def test_the_adc_starts_in_continuous_mode_on_the_requested_channel(fake_clock):
    bus = FakeI2C()

    Ads1115Pressure(bus, channel=2, clock=fake_clock)

    address, register, data = bus.writes[0]
    config = (data[0] << 8) | data[1]
    assert address == 0x48
    assert register == 0x01
    assert config & 0x8000  # start conversions
    assert (config >> 12) & 0b111 == 0b110  # AIN2, single-ended
    assert (config >> 9) & 0b111 == 0b001  # full scale +-4.096 V
    assert (config >> 8) & 0b1 == 0  # continuous, so reads never block
    assert (config >> 5) & 0b111 == 0b100  # 128 SPS
    assert config & 0b11 == 0b11  # comparator disabled


def test_the_first_conversions_are_not_trusted(fake_clock):
    sensor = Ads1115Pressure(FakeI2C(raw=_raw(1.25)), clock=fake_clock)

    reading = sensor.read_pressure()

    assert reading.ok is False
    assert reading.fault is not None
    assert "warming up" in reading.fault


def test_a_voltage_becomes_bar(fake_clock):
    sensor = _sensor(FakeI2C(raw=_raw(1.25)), fake_clock)

    reading = sensor.read_pressure()

    assert reading.ok is True
    assert reading.fault is None
    assert reading.bar == pytest.approx(8.0)


def test_the_configured_divider_is_applied(fake_clock):
    sensor = _sensor(
        FakeI2C(raw=_raw(2.5)),
        fake_clock,
        transducer=PressureTransducer(divider=1.0),
    )

    assert sensor.read_pressure().bar == pytest.approx(8.0)


def test_an_unplugged_sender_is_a_fault_not_zero_bar(fake_clock):
    sensor = _sensor(FakeI2C(raw=0), fake_clock)

    reading = sensor.read_pressure()

    assert reading.ok is False
    assert reading.fault is not None
    assert "unplugged" in reading.fault


def test_an_overrange_signal_is_a_fault(fake_clock):
    sensor = _sensor(FakeI2C(raw=_raw(2.5)), fake_clock)

    reading = sensor.read_pressure()

    assert reading.ok is False
    assert reading.fault is not None
    assert "above" in reading.fault


def test_a_bus_error_becomes_a_fault(fake_clock):
    bus = FakeI2C()
    bus.fail_with = OSError("Remote I/O error")
    sensor = _sensor(bus, fake_clock)

    reading = sensor.read_pressure()

    assert reading.ok is False
    assert reading.fault is not None
    assert "Remote I/O error" in reading.fault


def test_a_short_read_becomes_a_fault(fake_clock):
    bus = FakeI2C()
    bus.payload = [0x12]
    sensor = _sensor(bus, fake_clock)

    reading = sensor.read_pressure()

    assert reading.ok is False
    assert reading.fault is not None
    assert "short I2C read" in reading.fault


def test_close_releases_the_bus():
    bus = FakeI2C()

    Ads1115Pressure(bus).close()

    assert bus.closed


@pytest.mark.parametrize(
    "kwargs",
    [
        {"address": 0x50},
        {"channel": 4},
        {"pga_volts": 3.0},
        {"data_rate": 100},
    ],
)
def test_an_invalid_ads1115_configuration_is_rejected(kwargs):
    with pytest.raises(ValueError):
        Ads1115Pressure(FakeI2C(), **kwargs)
