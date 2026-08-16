"""Lamport clock max-merge — the same formula the client uses after a pull
(plan §5.4): lamport = max(local_lamport, max(incoming lamports)).

Server side, this merges the server's current max lamport with the lamports
carried on an incoming push batch, so a client that pushes learns the
server's view of time in the same response.
"""

from collections.abc import Iterable


def merge_lamport(local: int, incoming: Iterable[int]) -> int:
    values = [local, *incoming]
    return max(values)
