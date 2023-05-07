from dotenv import load_dotenv

load_dotenv()

import os
from flask import Flask
from routes.avs_routes import avs_routes
from utils.limiter import limiter

app = Flask(__name__)
app.register_blueprint(avs_routes)
PORT = os.getenv("PORT")
limiter.init_app(app)


@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Vary"] = "Cookie"
    response.headers[
        "Strict-Transport-Security"
    ] = "max-age=31536000; includeSubDomains"
    response.headers["Server"] = None
    return response


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
