"""CamWatch — camera vision worker for the Safety Agent.

Default is one pass, not a loop. FAST/heuristic classifies Houston TranStar
JPEGs (flood/water) and POSTs Flask ``/api/alerts`` when that bus is up
(port 5001). ``--vision grok`` is a single classify then exit. ``--loop``
is opt-in and must not run overnight.

The alert JSON matches ``docs/SAFETY-AGENT-DESIGN.md`` and the Flask
``POST /api/alerts`` contract. ``XAI_API_KEY`` is optional.
A still that returns HTTP 404 can use a local one-frame MP4 the same way.
"""

__version__ = "0.1.0"
