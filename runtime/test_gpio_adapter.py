from __future__ import annotations

from runtime.adapters.gpio_relay import GPIORelayAdapter, RecordingDigitalOutput


def test_gpio_adapter_maps_approved_relay_commands() -> None:
    output = RecordingDigitalOutput()
    adapter = GPIORelayAdapter(output)

    adapter.apply(b"RELAY:ON")
    adapter.apply(b"RELAY:OFF")

    assert output.transitions == [True, False]
    assert output.value is False


def test_gpio_adapter_rejects_unknown_payload() -> None:
    output = RecordingDigitalOutput()
    adapter = GPIORelayAdapter(output)

    try:
        adapter.apply(b"RELAY:INVALID")
    except ValueError as exc:
        assert str(exc) == "unsupported relay payload"
    else:
        raise AssertionError("unknown relay payload must be rejected")

    assert output.transitions == []
