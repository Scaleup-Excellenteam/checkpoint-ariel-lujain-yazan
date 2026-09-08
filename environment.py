"""Process configuration shared by the server and local bridge."""

from pathlib import Path

from dotenv import load_dotenv


ROOT_ENV_FILE = Path(__file__).resolve().parent / ".env"


def load_root_env() -> bool:
    """Load the repository's optional root .env without replacing shell values.

    The explicit path keeps startup independent of the directory from which
    Uvicorn is invoked.  ``override=False`` lets a developer temporarily
    override any setting through the process environment.
    """
    return load_dotenv(ROOT_ENV_FILE, override=False)
