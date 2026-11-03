"""XWatch — fixture / RSS social watcher for the Safety Agent.

Issue #18. Publishes mock social items onto the port-8000 alert bus.
There is **no** live X/Twitter API call and **no** Grok swarm. A missing
``X_BEARER_TOKEN`` is expected; even if that env var is set this worker
ignores it and reads JSON fixtures or RSS only.

Done-when: a fixture tweet about Galveston flooding becomes an
``source: x`` alert.
"""

__version__ = "0.1.0"
