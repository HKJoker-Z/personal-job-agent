"""Version 2 application package."""

import os


APP_VERSION = os.getenv("APP_VERSION", "2.2.0").strip() or "2.2.0"
