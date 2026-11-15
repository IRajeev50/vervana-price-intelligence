"""The Book (M17): inventory & margin intelligence — the commercial decision layer.

Advisory only. Given real inventory lots and the costs of holding them, compute the
expected net realisation of holding vs selling now and emit a BUY/HOLD/RELEASE/WAIT/
REROUTE recommendation that always shows its evidence, assumptions, and what would
invalidate it. Nothing here executes a trade or moves stock.
"""
