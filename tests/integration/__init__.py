"""Integration tests for persistence, recovery, logging, and the view bridge.

Every test in this package works inside its own temporary directory with
injected fake clocks. Nothing sleeps, nothing reads real wall-clock or
monotonic time, and nothing writes outside its temporary directory.
"""
