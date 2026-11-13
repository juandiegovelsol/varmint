#!/usr/bin/env python3
"""
sandbox_proxy_bridge.py — expose the VM-loopback anonymizer proxy to docker containers.

Problem: the anonymizer proxy that holds the anonymized key listens on the VM's 127.0.0.1
(e.g. 127.0.0.1:8091, Claude format). Harbor runs the agent (and the Tier-3 rubric judge)
INSIDE a docker container, whose 127.0.0.1 is its own loopback — so an in-container
http://localhost:8091 fails with ConnectionRefused. The key is fine; it's a
container->host-loopback addressing gap.

Fix (mirrors tb-trial-runner v2): a host address the container CAN reach routes back to the
VM. This script runs a TCP forwarder that listens there and relays every connection to the
VM's 127.0.0.1:<proxy>. The caller then points the in-container ANTHROPIC_BASE_URL at
http(s)://<addr>:<listen-port> and the request lands on the proxy.

HOW NECESSARY THAT RELAY IS DEPENDS ON THE HOST, and the honest answer is measured, not
assumed. Under rootless docker, slirp4netns maps its gateway address (10.0.2.2) onto the
HOST's 127.0.0.1, so a container can reach a loopback-bound proxy at http://10.0.2.2:8091
with no forwarder at all — verified both directions on such a host (real proxy bytes from
inside a container; ConnectionRefused for the same address from the host itself, with the
listener bound to 127.0.0.1 alone). That mapping is a slirp4netns default that
`--disable-host-loopback` removes, and it does not exist under pasta or rootful docker. So
the caller PROBES for a usable address rather than relying on it.

On the SEALED trial path the forwarder is needed for a different and non-negotiable reason:
it terminates TLS. See below.

--------------------------------------------------------------------------------------------
TLS MODE (--tls-cert/--tls-key), and why the sealed trial NEEDS it
--------------------------------------------------------------------------------------------
Once the agent phase is sealed, `main` shares the netns of harbor's egress-control sidecar,
so every TCP connection is redirected into gost (the sidecar's transparent proxy) and matched
against the allowlist by SNIFFING the connection.

gost's *HTTP* sniffing handler does not tunnel — it terminates HTTP and applies its own
15-SECOND DEADLINE to reading the upstream response HEADERS. Measured, deterministically:
an upstream that takes 14s to send headers is fine; 16s and the client gets a clean EOF with
ZERO bytes at exactly 15.00s. To the agent that is a socket-layer failure with no HTTP
response at all — `API Error: Unable to connect to API (ECONNRESET)`, `error_status: null`
— and every retry dies the same way for as long as the model stays slow.

Only plaintext HTTP goes down that path. Measured on the same setup: a non-HTTP payload and
a TLS connection both survive 25s+ of upstream silence, because gost sniffs them (SNI, or
nothing at all), matches the allowlist by ADDRESS, and then forwards raw TCP with no
deadline. Body streaming is never the problem either — once headers are through, 30s gaps
between chunks relay indefinitely.

So in TLS mode the bridge terminates TLS on the container-facing side and relays plaintext
to the loopback proxy. The agent uses https://<addr>:<port>, gost tunnels it, and a slow
model turn is no longer a connection error. This also matches how harbor behaves against a
real API endpoint, which is HTTPS and so was never exposed to gost's HTTP handler.

Certificate: pass --tls-cert/--tls-key (generate one with an IP SAN for the address the
container dials). The client must trust it — NODE_EXTRA_CA_CERTS=<the cert> for Claude Code.

Binds 0.0.0.0 by default (so it's reachable from any docker network's gateway, not just the
default bridge) but advertises the address the container should dial. Preflights the upstream
first and prints one of:
    BRIDGE_READY http://<gateway>:<port>      (or https:// in TLS mode)
    BRIDGE_UPSTREAM_DOWN <reason>
Every connection is logged to stderr with byte counts and a close reason, so a mid-trial
teardown leaves evidence instead of vanishing. Runs until killed (SIGINT/SIGTERM). Pure stdlib.
"""
import argparse, os, socket, ssl, sys, threading, signal, time

_T0 = time.time()
_conn_seq = 0
_seq_lock = threading.Lock()


def log(msg):
    """Timestamped stderr line. Absolute clock + seconds-since-start: the first lines up
    with harbor's own logs, the second with the agent's api_retry offsets."""
    sys.stderr.write("[bridge %s +%8.2fs] %s\n"
                     % (time.strftime("%H:%M:%S"), time.time() - _T0, msg))
    sys.stderr.flush()


def relay(src, dst, tag, counter):
    """Copy src->dst until EOF. Returns nothing; records why it stopped in counter.

    Both directions shut BOTH sockets down on exit, which is what makes a half-close
    propagate. The reason is logged: this used to swallow every exception, so a teardown
    (the 30s-timeout bug, an upstream reset) left no trace at all.
    """
    reason = "eof"
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
            if not counter["chunks"]:
                counter["t_first"] = time.time() - counter["t0"]
            counter["n"] += len(data)
            counter["chunks"] += 1
    except (OSError, ssl.SSLError) as e:
        reason = "%s: %s" % (type(e).__name__, e)
    finally:
        counter["reason"] = reason
        if reason != "eof":
            log("%s ABORTED after %d bytes — %s" % (tag, counter["n"], reason))
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def handle(client, peer, up_host, up_port, tls_ctx):
    global _conn_seq
    with _seq_lock:
        _conn_seq += 1
        cid = _conn_seq
    t0 = time.time()

    if tls_ctx is not None:
        # Handshake in the worker thread, never in the accept loop: a client that connects
        # and then stalls must not block every other connection behind it.
        try:
            client = tls_ctx.wrap_socket(client, server_side=True)
        except (OSError, ssl.SSLError) as e:
            # Expected and harmless for the runner's own reachability probes, which do a
            # bare TCP connect and close without ever speaking TLS. Only worrying if it is
            # the agent's own address handshaking repeatedly.
            log("#%d %s TLS handshake failed after %.2fs: %s: %s "
                "(normal for a plain-TCP reachability probe)"
                % (cid, peer, time.time() - t0, type(e).__name__, e))
            try:
                client.close()
            except OSError:
                pass
            return

    try:
        upstream = socket.create_connection((up_host, up_port), timeout=30)
        # create_connection's timeout STAYS on the socket, so every later recv() in
        # relay() would raise TimeoutError after 30s of upstream silence — turned into a
        # shutdown of BOTH sockets, which the client sees as ECONNRESET. A model turn can
        # easily think for >30s before it starts streaming, so the 30s must apply to the
        # CONNECT only.
        upstream.settimeout(None)
    except OSError as e:
        log("#%d %s upstream connect to %s:%d FAILED after %.2fs: %s: %s"
            % (cid, peer, up_host, up_port, time.time() - t0, type(e).__name__, e))
        try:
            client.close()
        except OSError:
            pass
        return

    c2u = {"n": 0, "chunks": 0, "reason": "?", "t0": t0, "t_first": None}
    u2c = {"n": 0, "chunks": 0, "reason": "?", "t0": t0, "t_first": None}
    log("#%d %s open (upstream %s:%d in %.3fs)" % (cid, peer, up_host, up_port, time.time() - t0))
    t = threading.Thread(target=relay, args=(client, upstream, "#%d c->u" % cid, c2u),
                         daemon=True)
    t.start()
    relay(upstream, client, "#%d u->c" % cid, u2c)
    t.join(5)
    # ttfb = time from connect to the FIRST upstream byte. This is the number gost's HTTP
    # handler caps at 15s in plaintext mode, so it is the margin worth watching: a run whose
    # ttfb creeps toward 15s would have started failing on the old plaintext path.
    ttfb = u2c["t_first"]
    log("#%d %s closed after %.2fs — sent %dB/%d, recv %dB/%d, ttfb %s (c->u %s, u->c %s)%s"
        % (cid, peer, time.time() - t0, c2u["n"], c2u["chunks"], u2c["n"], u2c["chunks"],
           ("%.2fs" % ttfb) if ttfb is not None else "never",
           c2u["reason"], u2c["reason"],
           "  <-- would have been KILLED at 15s in plaintext mode"
           if ttfb is not None and ttfb > 15 else ""))


def preflight(up_host, up_port):
    try:
        s = socket.create_connection((up_host, up_port), timeout=5)
        s.close()
        return True, ""
    except OSError as e:
        return False, str(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--upstream-host", default="127.0.0.1")
    ap.add_argument("--upstream-port", type=int, default=8091)
    ap.add_argument("--listen-host", default="0.0.0.0",
                    help="interface to bind (0.0.0.0 = reachable from every docker gateway)")
    ap.add_argument("--listen-port", type=int, default=0,
                    help="0 = pick a free ephemeral port")
    ap.add_argument("--gateway", default="172.17.0.1",
                    help="the address the container should dial (advertised in BRIDGE_READY)")
    ap.add_argument("--tls-cert", default="",
                    help="PEM cert; enables TLS on the container-facing side so harbor's "
                         "egress sidecar tunnels the connection instead of parsing it as "
                         "HTTP (see the module docstring — gost caps plaintext HTTP "
                         "response headers at 15s)")
    ap.add_argument("--tls-key", default="", help="PEM private key for --tls-cert")
    args = ap.parse_args()

    tls_ctx = None
    scheme = "http"
    if args.tls_cert or args.tls_key:
        if not (args.tls_cert and args.tls_key):
            print("BRIDGE_UPSTREAM_DOWN tls needs both --tls-cert and --tls-key", flush=True)
            sys.exit(5)
        for p in (args.tls_cert, args.tls_key):
            if not os.path.exists(p):
                print("BRIDGE_UPSTREAM_DOWN tls file missing: %s" % p, flush=True)
                sys.exit(5)
        try:
            tls_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            tls_ctx.load_cert_chain(args.tls_cert, args.tls_key)
            # Select http/1.1 explicitly. The upstream anonymizer is HTTP/1.0, so h2 must
            # never be negotiated; without this the ServerHello carries no ALPN at all and
            # the client is left to guess, which is a needless ambiguity in a path where a
            # client that picks wrong would just hang.
            try:
                tls_ctx.set_alpn_protocols(["http/1.1"])
            except NotImplementedError:
                pass
        except (OSError, ssl.SSLError) as e:
            print("BRIDGE_UPSTREAM_DOWN tls cert load failed: %s" % e, flush=True)
            sys.exit(5)
        scheme = "https"

    ok, reason = preflight(args.upstream_host, args.upstream_port)
    if not ok:
        print(f"BRIDGE_UPSTREAM_DOWN {args.upstream_host}:{args.upstream_port} {reason}", flush=True)
        sys.exit(3)

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind((args.listen_host, args.listen_port))
    except OSError as e:
        print(f"BRIDGE_UPSTREAM_DOWN bind {args.listen_host}:{args.listen_port} {e}", flush=True)
        sys.exit(4)
    srv.listen(128)
    port = srv.getsockname()[1]
    print(f"BRIDGE_READY {scheme}://{args.gateway}:{port}", flush=True)
    log("%s:%d -> %s:%d  (container dials %s://%s:%d%s)"
        % (args.listen_host, port, args.upstream_host, args.upstream_port,
           scheme, args.gateway, port,
           ", TLS terminated here" if tls_ctx else ", PLAINTEXT"))

    def shutdown(*_):
        log("signal received — shutting down after %d connections" % _conn_seq)
        try:
            srv.close()
        except OSError:
            pass
        sys.exit(0)
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while True:
        try:
            client, peer = srv.accept()
        except OSError as e:
            log("accept loop ending: %s: %s" % (type(e).__name__, e))
            break
        threading.Thread(target=handle,
                         args=(client, "%s:%d" % peer, args.upstream_host,
                               args.upstream_port, tls_ctx),
                         daemon=True).start()


if __name__ == "__main__":
    main()
