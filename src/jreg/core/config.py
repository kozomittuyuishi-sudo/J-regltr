from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
import os

class Settings(BaseSettings):
    app_name: str = "J Regulator"
    debug: bool = False
    database_url: str = "sqlite:///./jregulator.db"
    config_dir: str = Field(default_factory=lambda: os.path.join(os.path.expanduser("~"), ".jreg"))
    
    model_config = SettingsConfigDict(env_prefix="JREG_")

settings = Settings()
