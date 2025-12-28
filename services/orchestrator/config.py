# config.py
"""
Configuration and environment setup for the orchestrator.
Handles environment variable loading, sanitization, and validation.
"""

import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI


def sanitize_url(url: str) -> str:
    """Sanitize URL by removing quotes, whitespace, and trailing slashes."""
    if not url:
        return url
    
    original = url
    sanitized = url.strip().strip('"').strip("'").strip('`')
    sanitized = sanitized.replace('\n', '').replace('\r', '').replace('\t', '')
    sanitized = sanitized.rstrip('/')
    
    if original != sanitized:
        print(f"🔧 URL sanitized: '{original}' -> '{sanitized}'")
    else:
        print(f"✅ URL: {sanitized}")
    
    return sanitized


def sanitize_api_key(key: str) -> str:
    """
    Sanitize OpenAI API key by removing whitespace, quotes, and non-ASCII characters.
    Validates format and provides debug output.
    """
    if not key:
        return key
    
    original_key = key
    original_length = len(key)
    
    # Remove leading/trailing whitespace and quotes
    sanitized = key.strip().strip('"').strip("'").strip('`')
    # Remove control characters
    sanitized = sanitized.replace('\n', '').replace('\r', '').replace('\t', '')
    # Remove all whitespace
    sanitized = ''.join(sanitized.split())
    # Remove non-printable characters
    sanitized = ''.join(char for char in sanitized if char.isprintable())
    
    # Check for non-ASCII characters
    non_ascii_chars = [c for c in sanitized if ord(c) > 127]
    if non_ascii_chars:
        print(f"   ⚠️  Warning: Found {len(non_ascii_chars)} non-ASCII characters in key")
        sanitized = ''.join(char for char in sanitized if ord(char) <= 127)
    
    # Debug output
    print(f"✅ OPENAI_API_KEY loaded")
    print(f"   Original length: {original_length}, Sanitized length: {len(sanitized)}")
    print(f"   Starts with: {sanitized[:10]}...")
    print(f"   Format check: starts with 'sk-' = {sanitized.startswith('sk-')}")
    print(f"   Contains only ASCII: {all(ord(c) <= 127 for c in sanitized)}")
    
    if original_length != len(sanitized):
        print(f"   ⚠️  Key was sanitized (removed {original_length - len(sanitized)} characters)")
    
    # Validate format
    if not sanitized.startswith("sk-"):
        print(f"   ❌ Invalid key format detected!")
        print(f"   First 20 chars (repr): {repr(sanitized[:20])}")
        print(f"   First 20 chars (raw): {sanitized[:20]}")
        raise ValueError(
            f"Invalid API key format. OpenAI API keys should start with 'sk-'. "
            f"Got: {sanitized[:15]}... (length: {len(sanitized)}). "
            f"Please check your .env file for extra characters, quotes, or formatting issues."
        )
    
    return sanitized


def get_mcp_server_url() -> str:
    """
    Determine MCP server URL based on environment.
    - Docker-to-Docker: use service name (mcp-server)
    - Docker-to-Host: use host.docker.internal
    - Local: use localhost
    """
    default_url = "http://mcp-server:8000"  # Default for Docker-to-Docker
    
    if os.getenv("DOCKER_ENV"):
        if os.getenv("MCP_ON_HOST", "false").lower() == "true":
            default_url = "http://host.docker.internal:8000"
    
    url = os.getenv("MCP_SERVER_URL", default_url)
    return sanitize_url(url)


def get_openai_api_key() -> str:
    """Load and validate OpenAI API key from environment."""
    # Load environment variables
    load_dotenv(override=False)  # Don't override existing env vars (set by Docker)
    
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        print("❌ OPENAI_API_KEY not found")
        print(f"   Current working directory: {os.getcwd()}")
        print(f"   Environment variables containing 'OPENAI': {[k for k in os.environ.keys() if 'OPENAI' in k.upper()]}")
        raise ValueError("OPENAI_API_KEY not found in environment variables.")
    
    # Sanitize and validate
    api_key = sanitize_api_key(api_key)
    
    # Ensure it's a string
    if not isinstance(api_key, str):
        api_key = str(api_key)
    
    # Final validation
    if len(api_key) < 20:  # OpenAI keys are typically 51+ characters
        raise ValueError(f"API key seems too short (length: {len(api_key)}). Please verify your key.")
    
    return api_key


def create_llm(api_key: str, model: str = "gpt-4o-mini", temperature: float = 0.0) -> ChatOpenAI:
    """
    Create and configure the OpenAI LLM instance.
    
    Args:
        api_key: OpenAI API key
        model: Model name (default: gpt-4o-mini)
        temperature: Temperature for generation (default: 0.0 for deterministic parsing)
    
    Returns:
        Configured ChatOpenAI instance
    """
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        temperature=temperature
    )


# Module-level configuration (loaded on import)
MCP_SERVER_URL = get_mcp_server_url()
OPENAI_API_KEY = get_openai_api_key()
llm = create_llm(OPENAI_API_KEY)

