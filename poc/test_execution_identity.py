import torch

from poc.execution_identity import BytesExecutionObject, digest_bytes, identify


def test_byte_execution_identity_is_exact_and_epoch_bound():
    packet = bytes(range(64))
    obj = BytesExecutionObject(packet)

    first = identify(obj, execution_epoch=481)
    second = identify(obj, execution_epoch=481)

    assert first == second
    assert first.digest == digest_bytes(packet)
    assert first.execution_epoch == 481


def test_same_bytes_have_same_identity_digest_across_object_instances():
    packet = b"A" * 64
    left = BytesExecutionObject(packet)
    right = BytesExecutionObject(bytes(packet))

    assert identify(left, 7).digest == identify(right, 7).digest


def test_changed_execution_bytes_change_identity():
    original = BytesExecutionObject(b"A" * 64)
    changed = BytesExecutionObject(b"A" * 63 + b"B")

    assert identify(original, 7).digest != identify(changed, 7).digest


def test_execution_identity_is_not_tensor_specific():
    action = torch.tensor([0.1, 0.2, 0.3])
    assert not hasattr(action, "canonical_bytes")
