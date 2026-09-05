"""Filesystem, database, and diagnostic-logging boundaries.

Nothing in this package decides a game rule. It resolves locations, commits
transactions, and records what happened; the authoritative state and its
revisions belong to ``scoreboard.application.service``.
"""
