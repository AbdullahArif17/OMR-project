import sys
from pathlib import Path

# Add the parent directory to sys.path so that local module imports work
sys.path.append(str(Path(__file__).resolve().parent.parent))

from main import app  # noqa: E402

async def vercel_app(scope, receive, send):
    if scope["type"] == "http":
        path = scope.get("path", "")
        if path.startswith("/api"):
            scope["path"] = path[4:] or "/"
    return await app(scope, receive, send)

# Expose the wrapped app
app = vercel_app