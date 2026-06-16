from datetime import datetime, timezone

from google.protobuf.timestamp_pb2 import Timestamp
from osprey.engine.executor.execution_context import Action, ExecutionResult
from osprey.engine.language_types.verdicts import VerdictEffect
from osprey.rpc.common.v1.verdicts_pb2 import Verdicts


def _action(
    action_id: int = 1,
    action_name: str = 'test_action',
    timestamp: datetime = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
) -> Action:
    return Action(action_id=action_id, action_name=action_name, data={}, timestamp=timestamp)


def _result(action: Action, verdicts: list[str]) -> ExecutionResult:
    effects = {VerdictEffect: [VerdictEffect(verdict=v) for v in verdicts]} if verdicts else {}
    return ExecutionResult(extracted_features={}, action=action, effects=effects, error_infos=[])


def test_fields_are_mapped_correctly() -> None:
    action = _action(action_id=99, action_name='guild_invite_created')
    proto = _result(action, ['reject', 'flag']).get_verdicts_pb2_proto()

    assert isinstance(proto, Verdicts)
    assert proto.action_id == 99
    assert proto.action_name == 'guild_invite_created'
    assert list(proto.verdicts) == ['reject', 'flag']


def test_timestamp_conversion() -> None:
    ts = datetime(2024, 1, 15, 10, 30, 45, 123456, tzinfo=timezone.utc)
    proto = _result(_action(timestamp=ts), []).get_verdicts_pb2_proto()

    expected = Timestamp()
    expected.FromDatetime(ts)
    assert proto.timestamp == expected


def test_no_verdicts() -> None:
    proto = _result(_action(), []).get_verdicts_pb2_proto()
    assert list(proto.verdicts) == []


def test_single_verdict() -> None:
    proto = _result(_action(), ['allow']).get_verdicts_pb2_proto()
    assert list(proto.verdicts) == ['allow']


def test_serialization_roundtrip() -> None:
    # Catches binary encoding changes between protobuf library versions.
    action = _action(action_id=42, action_name='test_event')
    proto = _result(action, ['reject']).get_verdicts_pb2_proto()

    roundtripped = Verdicts()
    roundtripped.ParseFromString(proto.SerializeToString())

    assert roundtripped.action_id == 42
    assert roundtripped.action_name == 'test_event'
    assert list(roundtripped.verdicts) == ['reject']
    assert roundtripped.timestamp == proto.timestamp
