from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import threading
import time
import urllib.request

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"message": "An unexpected server error occurred"},
    )

@app.post("/crash")
def crash():
    raise PermissionError("Read-only file system")

def run():
    uvicorn.run(app, host="127.0.0.1", port=8005, log_level="error")

if __name__ == "__main__":
    t = threading.Thread(target=run, daemon=True)
    t.start()
    time.sleep(1)

    req = urllib.request.Request(
        'http://127.0.0.1:8005/crash',
        method='POST',
        headers={'Origin': 'https://example.com'}
    )
    try:
        with urllib.request.urlopen(req) as response:
            pass
    except Exception as e:
        print('Status:', e.code)
        print('Headers:', e.headers)
