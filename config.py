import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    # Cohere API Configuration
    COHERE_API_KEY = os.getenv('COHERE_API_KEY', '4glbvTb64nuypgWkis8W5Q4eaN69mR3oA98pCSJa')
    
    # Flask Configuration
    SECRET_KEY = os.getenv('SECRET_KEY', 'Drmhze6EPcv0fN_81Bj-nA')
    DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 't')
    
    # File Upload Configuration
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB limit
    ALLOWED_EXTENSIONS = {'pdf', 'docx', 'doc', 'txt'}
    
    # API Configuration
    COHERE_MODEL = os.getenv('COHERE_MODEL', 'command-r-plus')
    COHERE_MAX_TOKENS = int(os.getenv('COHERE_MAX_TOKENS', 1000))
    COHERE_TEMPERATURE = float(os.getenv('COHERE_TEMPERATURE', 0.6))

# Instantiate the configuration
config = Config()