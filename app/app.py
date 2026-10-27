
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

try:
    import psycopg
except ImportError:
    psycopg = None

SECRET_FILE = os.getenv("SECRET_FILE", "/vault/secrets/app-config")
DB_SECRET_FILE = os.getenv("DB_SECRET_FILE", "/vault/secrets/db-creds")


def read_secret_status():
    try:
        with open(SECRET_FILE, encoding="utf-8") as file:
            content = file.read().splitlines()
        return {
            "secret_file_found": True,
            "username_present": any(x.startswith("Username: ") for x in content),
            "password_present": any(x.startswith("Password: ") for x in content),
        }
    except OSError:
        return {
            "secret_file_found": False,
            "username_present": False,
            "password_present": False,
        }


def check_database():
    if psycopg is None:
        return 503, {"database": "error", "message": "Database driver unavailable"}

    try:
        with open(DB_SECRET_FILE, encoding="utf-8") as file:
            credentials = json.load(file)

        username = credentials.get("username")
        password = credentials.get("password")
        if not username or not password:
            return 500, {"database": "error", "message": "Credentials missing"}

        with psycopg.connect(
            host="postgres.database.svc",
            port=5432,
            dbname="appdb",
            user=username,
            password=password,
            connect_timeout=5,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT message FROM vault_demo LIMIT 1")
                row = cursor.fetchone()

        return 200, {
            "database": "connected",
            "query_successful": True,
            "sample_row": row[0] if row else None,
        }
    except (OSError, ValueError, psycopg.Error):
        return 503, {
            "database": "error",
            "query_successful": False,
            "message": "Database check failed",
        }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            status, result = 200, {"status": "ok"}
        elif self.path == "/status":
            status, result = 200, read_secret_status()
        elif self.path == "/db-check":
            status, result = check_database()
        else:
            status, result = 404, {"error": "not found"}

        body = json.dumps(result).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"Application listening on port {port}", flush=True)
    server.serve_forever()
