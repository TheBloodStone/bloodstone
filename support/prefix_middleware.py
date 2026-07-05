"""Set SCRIPT_NAME when served behind an nginx path prefix (HTTPS only)."""


class PrefixMiddleware:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        script_name = (environ.get("HTTP_X_SCRIPT_NAME") or "").strip().rstrip("/")
        if script_name:
            environ["SCRIPT_NAME"] = script_name
        return self.app(environ, start_response)


def apply_prefix(app):
    from werkzeug.middleware.proxy_fix import ProxyFix

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    app.wsgi_app = PrefixMiddleware(app.wsgi_app)
    return app