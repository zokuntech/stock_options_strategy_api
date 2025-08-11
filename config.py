import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    APP_NAME: str = "Bull Put Credit Spread API"
    ENV: str = os.getenv("ENV", "local")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    PORT: int = int(os.getenv("PORT", "8000"))
    CORS_ALLOW_ORIGINS = os.getenv("CORS_ALLOW_ORIGINS", "*").split(",")

settings = Settings()
