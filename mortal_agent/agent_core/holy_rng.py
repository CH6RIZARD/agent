"""
TempleOS holy RNG: OS entropy + high-resolution timer jitter, mixed via SHA-256.
Deterministic integer stream per instance from RAM-only seed. Never persisted.
"""

import os
import time
import hashlib
from typing import Optional


def _collect_entropy(n_bytes: int = 32) -> bytes:
    """Collect entropy: os.urandom + perf_counter_ns timing jitter (multiple samples)."""
    parts = [os.urandom(max(16, n_bytes // 2))]
    for _ in range(8):
        t0 = time.perf_counter_ns()
        parts.append(os.urandom(4))
        t1 = time.perf_counter_ns()
        jitter = (t1 - t0) & 0xFFFF_FFFF
        parts.append(jitter.to_bytes(4, "big"))
    return b"".join(parts)


def seed_from_entropy(extra: Optional[bytes] = None) -> bytes:
    """
    Produce a 32-byte seed: SHA-256(entropy + optional extra).
    RAM only. Never log or expose.
    """
    raw = _collect_entropy(32)
    if extra:
        raw = raw + bytes(extra)[:64]
    return hashlib.sha256(raw).digest()


class HolyRNG:
    """
    Deterministic RNG stream from a seed. Seed from seed_from_entropy() at birth.
    RAM only. Never persist or expose stream values to agent/observer/LLM.
    """

    def __init__(self, seed: Optional[bytes] = None):
        if seed is None:
            seed = seed_from_entropy()
        self._state = bytearray(hashlib.sha256(seed).digest())
        self._counter = 0

    def _next_block(self) -> bytes:
        """Next 32-byte block. SHA-256(state || counter)."""
        self._counter += 1
        block = hashlib.sha256(self._state + self._counter.to_bytes(8, "big")).digest()
        self._state[:] = block
        return block

    def random_bytes(self, n: int) -> bytes:
        """Return n bytes from the stream."""
        out = []
        while len(out) < n:
            out.append(self._next_block())
        return b"".join(out)[:n]

    def uniform_01(self) -> float:
        """Uniform [0, 1) from next 8 bytes."""
        b = self.random_bytes(8)
        v = int.from_bytes(b, "big") & ((1 << 53) - 1)
        return v / (1 << 53)

    def randint(self, a: int, b: int) -> int:
        """Inclusive [a, b]. Uses rejection for uniformity."""
        if a > b:
            a, b = b, a
        span = b - a + 1
        if span <= 0:
            return a
        max_val = (1 << 53) - 1
        limit = (max_val // span) * span
        while True:
            v = int.from_bytes(self.random_bytes(7), "big") & max_val
            if v < limit:
                return a + (v % span)

    def shuffle(self, seq: list) -> None:
        """Fisher-Yates in-place shuffle. Deterministic with this RNG."""
        n = len(seq)
        for i in range(n - 1, 0, -1):
            j = self.randint(0, i)
            seq[i], seq[j] = seq[j], seq[i]
