import secrets

# api_key = secrets.token_urlsafe(32)


def generate_api_key(length=32):
    """Generates a random API key of specified length.

    Args:
        length (int): The length of the API key to generate. Defaults to 32.

    Returns:
        str: A random API key of the specified length.
    """
    return secrets.token_hex(length)
