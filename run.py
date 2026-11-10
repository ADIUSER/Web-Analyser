from sqlalchemy import true

from app import create_app

app = create_app()

if __name__ == "__main__":
    # Debug is deliberately off by default; enable only in a trusted local environment.
    app.run(host="127.0.0.1", port=5000, debug=True, threaded=True)
