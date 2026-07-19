"""WSGI entry point used by gunicorn in production:

    gunicorn --workers 1 --threads 4 --bind 127.0.0.1:8099 wsgi:application
"""
from gymapp import create_app

application = create_app()

if __name__ == "__main__":
    application.run(host="127.0.0.1", port=5000, debug=True)
