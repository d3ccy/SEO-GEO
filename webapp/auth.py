from functools import wraps
from flask import request, Response


def requires_auth(password_getter):
    """Decorator factory that enforces HTTP Basic Auth if APP_PASSWORD is set."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            app_password = password_getter()
            if not app_password:
                return f(*args, **kwargs)  # auth disabled
            auth = request.authorization
            if not auth or auth.password != app_password:
                return Response(
                    'Authentication required.',
                    401,
                    {'WWW-Authenticate': 'Basic realm="SEO-GEO Toolkit"'},
                )
            return f(*args, **kwargs)
        return decorated
    return decorator
