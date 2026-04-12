# backend/main.py
import os
import uvicorn
from app import create_app

app = create_app()

if __name__ == "__main__":
    host = os.getenv("BACKEND_HOST", "127.0.0.1")
    port = int(os.getenv("BACKEND_PORT", 8000))
    uvicorn.run("main:app", host=host, port=port, reload=True, factory=False)
