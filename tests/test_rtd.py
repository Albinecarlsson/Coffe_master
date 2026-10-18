from __future__ import annotations

import pytest

from espresso_mod.domain.rtd import (
    PT100_R0,
    PT1000_R0,
    celsius_to_resistance,
    resistance_to_celsius,
)
from espresso_mod.hal.rtd_max31865 import Max31865RtdSensor

_REG_CONFIG = 0x00
_REG_RTD_MSB = 0x01
_REG_RTD_LSB = 0x02
_REG_FAULT_STATUS = 0x07

_CFG_VBIAS_ON = 0x80
_CFG_AUTO_CONVERT = 0x40
_CFG_THREE_WIRE = 0x10
_CFG_FAULT_CLEAR = 0x02
_CFG_FILTER_50HZ = 0x01

_ADC_FULL_SCALE = 32768


class FakeSpi:
    """Minimal MAX31865 register emulation with an spidev-style ``xfer2``."""

    def __init__(self, rref: float = 430.0) -> None:
        self.rref = rref
        self.registers = dict.fromkeys(range(8), 0)
        self.transactions: list[list[int]] = []

    def xfer2(self, data: list[int]) -> list[int]:
        self.transactions.append(list(data))
        address = data[0]
        if address & 0x80:  # write
            self.registers[address & 0x7F] = data[1] & 0xFF
            return [0x00, 0x00]
        return [0x00, self.registers[address & 0x7F]]

    # ---- test helpers ----

    def set_resistance(self, ohms: float, *, fault: bool = False) -> None:
        code = int(round(ohms / self.rref * _ADC_FULL_SCALE)) & 0x7FFF
        raw = (code << 1) | (1 if fault else 0)
        self.registers[_REG_RTD_MSB] = (raw >> 8) & 0xFF
        self.registers[_REG_RTD_LSB] = raw & 0xFF

    def set_celsius(self, celsius: float, r0: float = PT100_R0, *, fault: bool = False) -> None:
        self.set_resistance(celsius_to_resistance(celsius, r0), fault=fault)

    def writes_to(self, register: int) -> list[int]:
        return [frame[1] for frame in self.transactions if frame[0] == register | 0x80]


def _make_sensor(spi, fake_clock, **kwargs):
    """Build a sensor and step past its conversion warm-up window."""
    sensor = Max31865RtdSensor(spi, clock=fake_clock, **kwargs)
    fake_clock.sleep(1.0)
    return sensor


# ---- readings ----


@pytest.mark.parametrize("celsius", [-50.0, 0.0, 20.0, 93.0, 140.0])
def test_reads_temperature_across_range(fake_clock, celsius):
    spi = FakeSpi()
    spi.set_celsius(celsius)
    sensor = _make_sensor(spi, fake_clock)

    reading = sensor.read()

    assert reading.ok is True
    assert reading.fault is None
    assert reading.celsius == pytest.approx(celsius, abs=0.1)


def test_pt1000_uses_its_own_nominal_resistance(fake_clock):
    spi = FakeSpi(rref=4300.0)
    spi.set_celsius(93.0, r0=PT1000_R0)
    sensor = _make_sensor(spi, fake_clock, r0=PT1000_R0, rref=4300.0)

    assert sensor.read().celsius == pytest.approx(93.0, abs=0.1)


def test_read_does_not_wait_for_a_conversion(fake_clock):
    """Auto-convert mode means a read is a register access, never a blocking wait."""
    spi = FakeSpi()
    spi.set_celsius(93.0)
    sensor = _make_sensor(spi, fake_clock)

    before = fake_clock.now()
    sensor.read()

    assert fake_clock.now() == before


def test_first_read_before_conversion_is_not_ok(fake_clock):
    spi = FakeSpi()
    spi.set_celsius(93.0)
    sensor = Max31865RtdSensor(spi, clock=fake_clock)

    warming = sensor.read()
    assert warming.ok is False
    assert "warming up" in (warming.fault or "")

    fake_clock.sleep(0.1)
    assert sensor.read().ok is True


# ---- configuration ----


def test_bias_and_auto_convert_are_enabled(fake_clock):
    spi = FakeSpi()

    Max31865RtdSensor(spi, clock=fake_clock)

    written = spi.writes_to(_REG_CONFIG)
    assert written
    assert all(value & _CFG_VBIAS_ON for value in written)
    assert all(value & _CFG_AUTO_CONVERT for value in written)


def test_three_wire_enables_lead_compensation(fake_clock):
    spi = FakeSpi()

    Max31865RtdSensor(spi, clock=fake_clock, wires=3)

    assert spi.registers[_REG_CONFIG] & _CFG_THREE_WIRE


def test_two_and_four_wire_leave_compensation_off(fake_clock):
    for wires in (2, 4):
        spi = FakeSpi()
        Max31865RtdSensor(spi, clock=fake_clock, wires=wires)
        assert not spi.registers[_REG_CONFIG] & _CFG_THREE_WIRE


def test_filter_frequency_bit(fake_clock):
    spi_50 = FakeSpi()
    Max31865RtdSensor(spi_50, clock=fake_clock, filter_hz=50)
    assert spi_50.registers[_REG_CONFIG] & _CFG_FILTER_50HZ

    spi_60 = FakeSpi()
    Max31865RtdSensor(spi_60, clock=fake_clock, filter_hz=60)
    assert not spi_60.registers[_REG_CONFIG] & _CFG_FILTER_50HZ


def test_spi_frames_use_the_write_bit(fake_clock):
    spi = FakeSpi()
    sensor = _make_sensor(spi, fake_clock)

    sensor.read()

    writes = [frame for frame in spi.transactions if frame[0] & 0x80]
    reads = [frame for frame in spi.transactions if not frame[0] & 0x80]
    assert writes and all(len(frame) == 2 for frame in writes)
    assert reads and all(frame[1] == 0x00 for frame in reads)


@pytest.mark.parametrize("wires", [0, 1, 5])
def test_invalid_wire_count_rejected(fake_clock, wires):
    with pytest.raises(ValueError, match="wires"):
        Max31865RtdSensor(FakeSpi(), clock=fake_clock, wires=wires)


@pytest.mark.parametrize("filter_hz", [0, 49, 61])
def test_invalid_filter_rejected(fake_clock, filter_hz):
    with pytest.raises(ValueError, match="filter_hz"):
        Max31865RtdSensor(FakeSpi(), clock=fake_clock, filter_hz=filter_hz)


def test_non_positive_reference_rejected(fake_clock):
    with pytest.raises(ValueError, match="positive"):
        Max31865RtdSensor(FakeSpi(), clock=fake_clock, rref=0.0)


# ---- faults ----


def test_fault_bit_is_decoded(fake_clock):
    spi = FakeSpi()
    spi.set_resistance(100.0, fault=True)
    spi.registers[_REG_FAULT_STATUS] = 0x80 | 0x04  # high threshold + over/under-voltage
    sensor = _make_sensor(spi, fake_clock)

    reading = sensor.read()

    assert reading.ok is False
    assert "high fault threshold" in (reading.fault or "")
    assert "overvoltage" in (reading.fault or "")


def test_fault_read_clears_the_latched_status(fake_clock):
    spi = FakeSpi()
    spi.set_resistance(100.0, fault=True)
    spi.registers[_REG_FAULT_STATUS] = 0x80
    sensor = _make_sensor(spi, fake_clock)
    before = len(spi.writes_to(_REG_CONFIG))

    sensor.read()

    clears = [v for v in spi.writes_to(_REG_CONFIG)[before:] if v & _CFG_FAULT_CLEAR]
    assert clears, "a faulted read must write the fault-clear bit"


def test_unrecognised_fault_bits_still_report(fake_clock):
    spi = FakeSpi()
    spi.set_resistance(100.0, fault=True)
    spi.registers[_REG_FAULT_STATUS] = 0x00
    sensor = _make_sensor(spi, fake_clock)

    reading = sensor.read()

    assert reading.ok is False
    assert "0x00" in (reading.fault or "")


def test_full_scale_reading_is_rejected(fake_clock):
    """A disconnected probe reads close to full scale, not a temperature."""
    spi = FakeSpi()
    spi.set_resistance(429.0)
    sensor = _make_sensor(spi, fake_clock)

    reading = sensor.read()

    assert reading.ok is False
    assert "outside" in (reading.fault or "")


def test_zero_reading_is_rejected(fake_clock):
    spi = FakeSpi()
    spi.set_resistance(0.0)
    sensor = _make_sensor(spi, fake_clock)

    assert sensor.read().ok is False


# ---- Callendar-Van Dusen maths ----


def test_pt100_known_resistances():
    assert celsius_to_resistance(0.0, PT100_R0) == pytest.approx(100.0, abs=0.001)
    assert celsius_to_resistance(100.0, PT100_R0) == pytest.approx(138.51, abs=0.01)
    assert celsius_to_resistance(-200.0, PT100_R0) == pytest.approx(18.52, abs=0.01)


def test_pt1000_scales_with_r0():
    assert celsius_to_resistance(100.0, PT1000_R0) == pytest.approx(1385.1, abs=0.1)


@pytest.mark.parametrize("celsius", [-200.0, -100.0, -50.0, -0.1, 0.0, 25.0, 93.0, 300.0, 850.0])
def test_round_trip_is_exact(celsius):
    resistance = celsius_to_resistance(celsius, PT100_R0)
    assert resistance_to_celsius(resistance, PT100_R0) == pytest.approx(celsius, abs=1e-6)


@pytest.mark.parametrize("celsius", [-200.0, -50.0, 93.0, 850.0])
def test_round_trip_is_exact_for_pt1000(celsius):
    resistance = celsius_to_resistance(celsius, PT1000_R0)
    assert resistance_to_celsius(resistance, PT1000_R0) == pytest.approx(celsius, abs=1e-6)


@pytest.mark.parametrize("resistance", [0.0, -5.0])
def test_non_positive_resistance_rejected(resistance):
    with pytest.raises(ValueError, match="positive"):
        resistance_to_celsius(resistance, PT100_R0)


def test_impossible_resistance_rejected():
    with pytest.raises(ValueError, match="out of range"):
        resistance_to_celsius(50_000.0, PT100_R0)
