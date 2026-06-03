"""
client.py - HTTP Client (TCP via Proxy) + UDP QoS Pinger
Jaringan Komputer - Tugas Besar

Cara pakai:
  python3 client.py                          → jalankan TCP + UDP
  python3 client.py --mode tcp               → HTTP request saja
  python3 client.py --mode tcp --path /osi.html
  python3 client.py --mode udp --count 10    → QoS ping saja
  python3 client.py --mode multi             → simulasi 5 client serentak

  Beda laptop (ganti IP):
  python3 client.py --proxy 192.168.1.11 --server 192.168.1.10
"""

import socket
import time
import argparse
import math
import datetime

# ─── Konfigurasi ─────────────────────────────────────────────────────────────────
# !! GANTI sesuai IP laptop proxy dan web server !!
PROXY_HOST  = '127.0.0.1'   # IP laptop yang jalankan proxy.py
PROXY_PORT  = 8080
SERVER_HOST = '127.0.0.1'   # IP laptop yang jalankan webserver.py (untuk UDP)
UDP_PORT    = 9000
UDP_TIMEOUT = 1.0            # maks 1 detik per paket

# ════════════════════════════════════════════════════════════════════════════════
#  MODE TCP — HTTP Request via Proxy
# ════════════════════════════════════════════════════════════════════════════════
def http_get(path="/index.html"):
    print(f"\n{'='*60}")
    print(f"  HTTP GET {path}")
    print(f"  Via proxy: {PROXY_HOST}:{PROXY_PORT}")
    print(f"{'='*60}")

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((PROXY_HOST, PROXY_PORT))

        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {PROXY_HOST}:{PROXY_PORT}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        )
        t0 = time.time()
        s.sendall(request.encode())

        response = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            response += chunk
        elapsed_ms = (time.time() - t0) * 1000
        s.close()

        # Pisahkan header dan body
        if b"\r\n\r\n" in response:
            header_raw, body = response.split(b"\r\n\r\n", 1)
        else:
            header_raw, body = response, b""

        headers = header_raw.decode("utf-8", errors="replace")
        status_line = headers.split("\r\n")[0]

        print(f"\nStatus  : {status_line}")
        print(f"RTT     : {elapsed_ms:.2f} ms")
        print(f"Ukuran  : {len(response)} bytes total ({len(body)} bytes body)")
        print(f"\n--- Header ---\n{headers}")

        # Tampilkan body HTML (potong kalau panjang)
        body_text = body.decode("utf-8", errors="replace")
        preview = body_text[:600]
        suffix  = "\n...[sisa konten dipotong]..." if len(body_text) > 600 else ""
        print(f"\n--- Body ---\n{preview}{suffix}")
        return elapsed_ms

    except ConnectionRefusedError:
        print(f"\n[ERROR] Koneksi ditolak.")
        print(f"        Pastikan proxy sudah berjalan di {PROXY_HOST}:{PROXY_PORT}")
    except socket.timeout:
        print(f"\n[ERROR] Timeout — proxy tidak merespons dalam 5 detik.")
    except Exception as e:
        print(f"\n[ERROR] {e}")
    return None

# ════════════════════════════════════════════════════════════════════════════════
#  MODE UDP — QoS Pinger
# ════════════════════════════════════════════════════════════════════════════════
def udp_ping(count=10):
    print(f"\n{'='*60}")
    print(f"  UDP QoS Ping")
    print(f"  Target: {SERVER_HOST}:{UDP_PORT}  |  Jumlah paket: {count}")
    print(f"{'='*60}\n")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(UDP_TIMEOUT)

    rtts   = []
    lost   = 0
    total_bytes = 0
    t_start = time.time()

    for seq in range(1, count + 1):
        ts_send    = time.time()
        payload    = f"Ping {seq} {ts_send}".encode()

        try:
            sock.sendto(payload, (SERVER_HOST, UDP_PORT))
            t_send = time.time()
            data, _ = sock.recvfrom(1024)
            t_recv = time.time()

            rtt = (t_recv - t_send) * 1000
            rtts.append(rtt)
            total_bytes += len(data)
            print(f"  [{seq:2d}] RTT = {rtt:.3f} ms  ({len(data)} bytes)")

        except socket.timeout:
            lost += 1
            print(f"  [{seq:2d}] Request timed out ⏱")

        time.sleep(0.1)

    duration = time.time() - t_start
    sock.close()

    # ── Hitung statistik QoS ──────────────────────────────────────────────────
    received  = len(rtts)
    loss_pct  = (lost / count) * 100

    # Jitter = deviasi standar selisih RTT berurutan
    jitter = 0.0
    if len(rtts) >= 2:
        diffs    = [abs(rtts[i] - rtts[i-1]) for i in range(1, len(rtts))]
        avg_diff = sum(diffs) / len(diffs)
        jitter   = math.sqrt(sum((d - avg_diff)**2 for d in diffs) / len(diffs))

    throughput = (total_bytes * 8 / 1000) / duration if duration > 0 else 0

    print(f"\n{'─'*45}")
    print(f"  Statistik QoS — {count} paket dikirim, {received} diterima")
    print(f"{'─'*45}")
    if rtts:
        print(f"  RTT Min    : {min(rtts):.3f} ms")
        print(f"  RTT Avg    : {sum(rtts)/len(rtts):.3f} ms")
        print(f"  RTT Max    : {max(rtts):.3f} ms")
    else:
        print("  RTT        : N/A (semua paket hilang!)")
    print(f"  Jitter     : {jitter:.3f} ms")
    print(f"  Packet Loss: {lost}/{count} = {loss_pct:.1f}%")
    print(f"  Throughput : {throughput:.2f} kbps")
    print(f"  Durasi     : {duration:.2f} detik")
    print(f"{'─'*45}\n")

    return rtts, loss_pct, jitter, throughput

# ════════════════════════════════════════════════════════════════════════════════
#  MODE MULTI — simulasi 5 client serentak
# ════════════════════════════════════════════════════════════════════════════════
def multi_client_test(n=5):
    import threading
    print(f"\n{'='*60}")
    print(f"  SIMULASI MULTI-CLIENT ({n} request serentak)")
    print(f"  Via proxy: {PROXY_HOST}:{PROXY_PORT}")
    print(f"{'='*60}\n")

    # Berbagai halaman supaya ada MISS dan HIT
    pages = ["/index.html", "/osi.html", "/tcpip.html", "/qos.html", "/implementation.html"]
    results = {}

    def worker(i, path):
        t0 = time.time()
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(10)
            s.connect((PROXY_HOST, PROXY_PORT))
            req = (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {PROXY_HOST}\r\n"
                f"Connection: close\r\n\r\n"
            )
            s.sendall(req.encode())
            resp = b""
            while True:
                c = s.recv(4096)
                if not c: break
                resp += c
            s.close()
            elapsed = (time.time() - t0) * 1000
            status  = resp.split(b"\r\n")[0].decode("utf-8", errors="replace")
            results[i] = (status, elapsed, len(resp))
            print(f"  [Client {i+1}] {path:25s}  {status}  —  {elapsed:.1f} ms  —  {len(resp)} bytes")
        except Exception as e:
            results[i] = (f"ERROR: {e}", 0, 0)
            print(f"  [Client {i+1}] ERROR: {e}")

    threads = [threading.Thread(target=worker, args=(i, pages[i % len(pages)])) for i in range(n)]
    for t in threads: t.start()
    for t in threads: t.join()

    ok = sum(1 for r in results.values() if "200" in str(r[0]))
    print(f"\n  Hasil: {ok}/{n} berhasil (200 OK)\n")

# ════════════════════════════════════════════════════════════════════════════════
#  Entry point
# ════════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Client — Tugas Besar Jarkom")
    parser.add_argument("--mode",   choices=["tcp","udp","both","multi"], default="both")
    parser.add_argument("--path",   default="/index.html", help="Path HTTP (mode tcp)")
    parser.add_argument("--count",  type=int, default=10,  help="Jumlah paket UDP")
    parser.add_argument("--proxy",  default=PROXY_HOST,    help="IP Proxy")
    parser.add_argument("--server", default=SERVER_HOST,   help="IP Web Server (UDP)")
    args = parser.parse_args()

    PROXY_HOST  = args.proxy
    SERVER_HOST = args.server

    print(f"\n  Client — Tugas Besar Jaringan Komputer")
    print(f"  {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    if args.mode in ("tcp", "both"):
        http_get(args.path)

    if args.mode in ("udp", "both"):
        udp_ping(args.count)

    if args.mode == "multi":
        multi_client_test(5)
