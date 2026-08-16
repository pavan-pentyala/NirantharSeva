from app.sync.lamport import merge_lamport


def test_merge_with_no_incoming_returns_local():
    assert merge_lamport(5, []) == 5


def test_merge_takes_higher_incoming_value():
    assert merge_lamport(5, [7]) == 7


def test_merge_keeps_local_when_incoming_is_lower():
    assert merge_lamport(10, [3, 4]) == 10


def test_merge_takes_max_of_many_incoming():
    assert merge_lamport(0, [3, 9, 2, 17, 5]) == 17


def test_merge_handles_ties():
    assert merge_lamport(8, [8, 8]) == 8


def test_merge_starts_from_zero():
    assert merge_lamport(0, [0]) == 0
