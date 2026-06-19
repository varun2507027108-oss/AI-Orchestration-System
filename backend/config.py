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

    # Generic Models
    GROQ_MODEL: str = Field(default="llama-3.3-70b-versatile")
    GEMINI_MODEL: str = Field(default="gemini-2.5-flash")
    NVIDIA_NIM_MODEL: str = Field(default="nvidia/llama-3.1-nemotron-70b-instruct")
    
    # Agent-Specific Models
    ADVISOR_MODEL: str = Field(default="")
    RESEARCHER_MODEL: str = Field(default="meta-llama/llama-4-scout-17b-16e-instruct")
    PM_MODEL: str = Field(default="")
    ARCHITECT_MODEL: str = Field(default="z-ai/glm-5.1")
    EM_MODEL: str = Field(default="z-ai/glm-5.1")
    MARKETING_MODEL: str = Field(default="")
    
    # Tool Configs
    GITHUB_TOKEN: str = Field(default="")
    NOTION_TOKEN: str = Field(default="")
    NOTION_DATABASE_ID: str = Field(default="")
    
    # Server Configs
    NEXT_PUBLIC_BACKEND_URL: str = Field(default="")
    ALLOWED_ORIGIN: str = Field(default="http://localhost:3000")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
