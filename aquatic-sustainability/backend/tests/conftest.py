import os
import sys
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-secret-for-notify-bus")
os.environ.setdefault("NOTIFY_DRY_RUN", "1")

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import pytest
from flask import Flask


@pytest.fixture(autouse=True)
def app():
    from app.alertbus import bp as alertbus_bp
    from app.alertbus import bus
    from app.notify import bp as notify_bp
    from app.notify import reset_logs
    from app.places import bp as places_bp

    bus.reset()
    reset_logs()
    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "test-secret-for-notify-bus"
    flask_app.register_blueprint(alertbus_bp, url_prefix="/api")
    flask_app.register_blueprint(notify_bp, url_prefix="/api")
    flask_app.register_blueprint(places_bp, url_prefix="/api")
    yield flask_app
    bus.reset()
    reset_logs()


@pytest.fixture
def client(app):
    return app.test_client()
