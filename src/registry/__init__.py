"""Declarative skill registry: each internal process is declared as a
typed skill (its inputs, scoped tools, and judgment points) and run by
one deterministic orchestrator in engine.py, rather than one hand-written
Python function per task type as supervisor_orchestrator.py has. See
README, "Declarative Skill Registry Extension"."""
