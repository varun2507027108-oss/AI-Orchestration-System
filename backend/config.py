# Application Configuration Settings
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    # API Keys
    GROQ_API_KEY: str = Field(default="")
    GEMINI_API_KEY: str = Field(default="")
    NVIDIA_NIM_API_KEY: str = Field(default="")
    TAVILY_API_KEY: str = Field(default="")
    
    # Agent-Specific API Keys
    ADVISOR_API_KEY: str = Field(default="")
    RESEARCHER_API_KEY: str = Field(default="")
    PM_API_KEY: str = Field(default="")
    ARCHITECT_API_KEY: str = Field(default="")
    EM_API_KEY: str = Field(default="")
    MARKETING_API_KEY: str = Field(default="")
    
    # Tool Configs
    GITHUB_TOKEN: str = Field(default="")
    NOTION_TOKEN: str = Field(default="")
    NOTION_DATABASE_ID: str = Field(default="")
    
    # Server Configs
    NEXT_PUBLIC_BACKEND_URL: str = Field(default="")
    ALLOWED_ORIGIN: str = Field(default="http://localhost:3000")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
