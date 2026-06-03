"""
webserver.py - HTTP Web Server (TCP port 8000) + UDP Echo Server (port 9000)
Jaringan Komputer - Tugas Besar

Letakkan file ini DI DALAM folder HTML/ dari asprak, atau
atur WEB_ROOT di bawah sesuai lokasi folder HTML/.
"""

import socket
import threading
import os
import datetime
import mimetypes

# ─── Konfigurasi ────────────────────────────────────────────────────────────────
HOST        = '0.0.0.0'
HTTP_PORT   = 8000
UDP_PORT    = 9000

# Web root = folder HTML dari asprak
# Jika webserver.py diletakkan di DALAM folder HTML/, pakai:
#   WEB_ROOT = os.path.dirname(os.path.abspath(__file__))
# Jika webserver.py diletakkan DI LUAR folder HTML/ (satu level di atas), pakai:
#   WEB_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "HTML")
WEB_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "HTML")

# ─── Logging ─────────────────────────────────────────────────────────────────────
def log(client_ip, path, status, extra=""):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {client_ip:20s}  {str(status):5s}  {path}  {extra}")

# ─── Baca halaman error dari file asprak ─────────────────────────────────────────
def read_error_page(code):
    """Baca halaman error HTML dari folder status/ milik asprak."""
    path = os.path.join(WEB_ROOT, "status", f"{code}.html")
    try:
        with open(path, "rb") as f:
            return f.read()
    except:
        # Fallback kalau file error tidak ada
        return f"<html><body><h1>{code}</h1></body></html>".encode()

def error_response(code, text):
    body = read_error_page(code)
    header = (
        f"HTTP/1.1 {code} {text}\r\n"
        f"Content-Type: text/html; charset=utf-8\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    )
    return header.encode() + body

# ─── HTTP Response Builder ────────────────────────────────────────────────────────
def build_response(status_code, status_text, content_type, body_bytes):
    header = (
        f"HTTP/1.1 {status_code} {status_text}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body_bytes)}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    )
    return header.encode() + body_bytes

# ─── Handle satu koneksi TCP ─────────────────────────────────────────────────────
def handle_client(conn, addr):
    client_ip = addr[0]
    try:
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = conn.recv(4096)
            if not chunk:
                break
            data += chunk

        if not data:
            return

        request_line = data.split(b"\r\n")[0].decode("utf-8", errors="replace")
        parts = request_line.split()

        if len(parts) < 2 or parts[0] not in ("GET", "HEAD"):
            conn.sendall(error_response(400, "Bad Request"))
            log(client_ip, "-", 400)
            return

        method, url_path = parts[0], parts[1]

        # Hapus query string
        url_path = url_path.split("?")[0]

        # "/" → "/index.html"
        if url_path.endswith("/"):
            url_path += "index.html"

        # Cegah path traversal
        safe_path = os.path.normpath(url_path.lstrip("/"))
        file_path = os.path.join(WEB_ROOT, safe_path)

        if not os.path.abspath(file_path).startswith(os.path.abspath(WEB_ROOT)):
            conn.sendall(error_response(403, "Forbidden"))
            log(client_ip, url_path, 403)
            return

        if not os.path.isfile(file_path):
            conn.sendall(error_response(404, "Not Found"))
            log(client_ip, url_path, 404, "← File tidak ditemukan")
            return

        try:
            with open(file_path, "rb") as f:
                body = f.read()
            ctype, _ = mimetypes.guess_type(file_path)
            if ctype is None:
                ctype = "application/octet-stream"
            if "text" in ctype and "charset" not in ctype:
                ctype += "; charset=utf-8"
            response = build_response(200, "OK", ctype, body)
            conn.sendall(response)
            log(client_ip, url_path, 200, f"({len(body)} bytes)")
        except Exception as e:
            conn.sendall(error_response(500, "Internal Server Error"))
            log(client_ip, url_path, 500, str(e))

    except Exception as e:
        log(client_ip, "-", "ERR", str(e))
    finally:
        conn.close()

# ─── TCP HTTP Server ──────────────────────────────────────────────────────────────
def run_http_server():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, HTTP_PORT))
    srv.listen(50)
    print(f"[HTTP] Server running on port {HTTP_PORT} (TCP)")
    print(f"[HTTP] Melayani file dari: {WEB_ROOT}")
    while True:
        conn, addr = srv.accept()
        t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
        t.start()
        print(f"[HTTP] Thread baru untuk {addr[0]}:{addr[1]}")

# ─── UDP Echo Server ──────────────────────────────────────────────────────────────
def run_udp_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((HOST, UDP_PORT))
    print(f"[UDP]  Echo server running on port {UDP_PORT} (UDP)")
    while True:
        data, addr = sock.recvfrom(1024)
        sock.sendto(data, addr)  # echo balik payload identik
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[UDP]  {ts}  Echo {len(data)} bytes ← {addr[0]}:{addr[1]}")

# ─── Main ─────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  WEB SERVER — Tugas Besar Jaringan Komputer")
    print(f"  HTTP  : {HOST}:{HTTP_PORT}")
    print(f"  UDP   : {HOST}:{UDP_PORT}")
    print(f"  Root  : {WEB_ROOT}")
    print("=" * 60)

    # Cek apakah folder HTML ada
    if not os.path.isdir(WEB_ROOT):
        print(f"\n[ERROR] Folder HTML tidak ditemukan: {WEB_ROOT}")
        print("  Pastikan folder HTML/ ada di direktori yang sama dengan webserver.py")
        exit(1)

    t_http = threading.Thread(target=run_http_server, daemon=True)
    t_udp  = threading.Thread(target=run_udp_server,  daemon=True)
    t_http.start()
    t_udp.start()

    print("\n[INFO] Server siap. Tekan Ctrl+C untuk berhenti.\n")
    try:
        t_http.join()
    except KeyboardInterrupt:
        print("\n[INFO] Server dihentikan.")
