import os
from app import create_app
from app.roster import register_roster

# Define the app object at module level so Gunicorn can import it
app = create_app()
# Roster blueprint lives in app/roster.py. Register here so we do not edit
# app/__init__.py (#14/#35) or app/routes.py (#10). No Twilio send.
register_roster(app)

# Only run Flask’s dev server if executed directly (not under Gunicorn)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=False)
