def health() -> dict[str, str]:
    """Return a dependency-free process health payload."""
    return {"status": "ok", "service": "amath-bot"}
