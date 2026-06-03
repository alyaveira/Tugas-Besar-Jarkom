import socket
import threading
import os
import datetime
import hashlib
import time

# ─── Konfigurasi ─────────────────────────────────────────────────────────────────
HOST         = '0.0.0.0'
PROXY_PORT   = 8080

# !! GANTI ini dengan IP laptop yang menjalankan webserver.py !!
# Kalau satu laptop (testing lokal): biarkan 127.0.0.1
# Kalau beda laptop: misalnya '192.168.1.10'
SERVER_HOST  = '10.130.16.131'
SERVER_PORT  = 8000

TIMEOUT      = 5  # detik, timeout koneksi ke web server

# Folder untuk menyimpan cache (otomatis dibuat)
CACHE_DIR    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proxy_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# Lock supaya tidak race condition saat banyak thread akses cache bersamaan
cache_lock = threading.Lock()

# ─── Logging ─────────────────────────────────────────────────────────────────────
def log(client_ip, url, status, cache_status="", elapsed_ms=0):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tag = f"[{cache_status:5s}]" if cache_status else "      "
    print(f"[{ts}] {client_ip:20s}  {status:5s}  {tag}  {url}  ({elapsed_ms:.1f}ms)")

# ─── Cache helpers ────────────────────────────────────────────────────────────────
def cache_filename(url_path):
    """Nama file cache berdasarkan hash URL — aman untuk semua OS."""
    h = hashlib.md5(url_path.encode()).hexdigest()
    return os.path.join(CACHE_DIR, h + ".cache")

def cache_exists(url_path):
    return os.path.isfile(cache_filename(url_path))

def cache_read(url_path):
    with open(cache_filename(url_path), "rb") as f:
        return f.read()

def cache_write(url_path, data):
    with cache_lock:  # thread-safe
        with open(cache_filename(url_path), "wb") as f:
            f.write(data)

# ─── Halaman error proxy ──────────────────────────────────────────────────────────
def proxy_error(code, text):
    body = (
        f"<html><body>"
        f"<h1>{code} {text}</h1>"
        f"<p>Proxy tidak dapat menghubungi web server.</p>"
        f"</body></html>"
    ).encode()
    return (
        f"HTTP/1.1 {code} {text}\r\n"
        f"Content-Type: text/html; charset=utf-8\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: close\r\n\r\n"
    ).encode() + body

# ─── Parse URL path dari baris pertama request ───────────────────────────────────
def parse_request(raw):
    try:
        first_line = raw.split(b"\r\n")[0].decode("utf-8", errors="replace")
        parts = first_line.split()
        if len(parts) >= 2:
            method = parts[0]
            path = parts[1].split("?")[0]  # buang query string
            return method, path
    except:
        pass
    return None, None

# ─── Forward request ke web server ───────────────────────────────────────────────
def forward_to_server(raw_request):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(TIMEOUT)
        s.connect((SERVER_HOST, SERVER_PORT))
        s.sendall(raw_request)

        response = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            response += chunk
        s.close()
        return response, None

    except socket.timeout:
        return None, "timeout"
    except ConnectionRefusedError:
        return None, "refused"
    except Exception as e:
        return None, str(e)

# ─── Tangani satu koneksi client ─────────────────────────────────────────────────
def handle_client(conn, addr):
    client_ip = addr[0]
    t0 = time.time()

    try:
        # Baca request dari client
        raw = b""
        conn.settimeout(5)
        while b"\r\n\r\n" not in raw:
            chunk = conn.recv(4096)
            if not chunk:
                break
            raw += chunk

        if not raw:
            conn.close()
            return

        method, url_path = parse_request(raw)
        if not method:
            conn.sendall(proxy_error(400, "Bad Request"))
            conn.close()
            return

        elapsed = lambda: (time.time() - t0) * 1000

        # ── Cek cache (hanya untuk GET) ──────────────────────────────────────────
        if method == "GET" and cache_exists(url_path):
            cached_data = cache_read(url_path)
            conn.sendall(cached_data)
            log(client_ip, url_path, "200", "HIT", elapsed())
            conn.close()
            return

        # ── Cache MISS: teruskan ke web server ───────────────────────────────────
        response, error = forward_to_server(raw)

        if error == "timeout":
            conn.sendall(proxy_error(504, "Gateway Timeout"))
            log(client_ip, url_path, "504", "ERR", elapsed())

        elif error is not None:
            conn.sendall(proxy_error(502, "Bad Gateway"))
            log(client_ip, url_path, "502", "ERR", elapsed())

        else:
            # Ambil status code dari response
            status_line = response.split(b"\r\n")[0].decode("utf-8", errors="replace")
            code = status_line.split()[1] if len(status_line.split()) > 1 else "???"

            # Simpan ke cache hanya jika 200 OK dan metode GET
            if method == "GET" and code == "200":
                cache_write(url_path, response)

            conn.sendall(response)
            log(client_ip, url_path, code, "MISS", elapsed())

    except Exception as e:
        print(f"[ERR] handle_client {addr}: {e}")
    finally:
        try:
            conn.close()
        except:
            pass

# ─── Main ─────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  PROXY SERVER — Tugas Besar Jaringan Komputer")
    print(f"  Listen   : {HOST}:{PROXY_PORT}")
    print(f"  Forward  : {SERVER_HOST}:{SERVER_PORT}")
    print(f"  Cache dir: {CACHE_DIR}")
    print("=" * 60)
    print()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PROXY_PORT))
    srv.listen(50)
    print(f"[PROXY] Listening di port {PROXY_PORT} — multithreading aktif")
    print(f"[PROXY] Tekan Ctrl+C untuk berhenti.\n")

    try:
        while True:
            conn, addr = srv.accept()
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()
            print(f"[PROXY] Koneksi baru dari {addr[0]}:{addr[1]} — thread spawned")
    except KeyboardInterrupt:
        print("\n[INFO] Proxy dihentikan.")
