from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Rate limit: 
limiter = Limiter(
  key_func = get_remote_address,
  default_limits = ["15 per hour"]
)
