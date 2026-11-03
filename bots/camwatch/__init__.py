"""CamWatch — camera vision worker for the Safety Agent.

Up to 8 cameras are eligible. Each pass pulls one new JPEG (every 15–30
seconds while looping), classifies it (standing water, overtopped road,
debris, smoke, all-clear), and POSTs ``/api/alerts`` only when the class
changes. Unchanged frames are not sent to Grok. ``GROK_MAX_RPM`` caps
vision calls (default 2/min, shared with the rest of the Safety Agent).

The alert JSON matches ``docs/SAFETY-AGENT-DESIGN.md`` and Devanshu's
``POST /api/alerts`` contract on issue #11. ``XAI_API_KEY`` is optional:
without it, a filename/sidecar fallback classifies demo frames so a
flooded-road image dropped in the test inbox still creates an alert.
A still that returns HTTP 404 can use a local one-frame MP4 the same way.
"""

__version__ = "0.1.0"
