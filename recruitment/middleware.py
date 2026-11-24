class PrivacyHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Django admin has its own UI requirements.
        if not request.path.startswith("/admin/"):
            response["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self'; "
                "connect-src 'self'; "
                "img-src 'self'; "
                "object-src 'none'; "
                "base-uri 'none'; "
                "frame-ancestors 'none'; "
                "form-action 'self'"
            )

        response["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )

        if not request.path.startswith("/static/"):
            response["Cache-Control"] = "no-store, private"

        return response
