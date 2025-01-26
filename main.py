from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from routes import app

from config import CORS_ORIGINS

# Set up CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS, 
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"], 
)

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
