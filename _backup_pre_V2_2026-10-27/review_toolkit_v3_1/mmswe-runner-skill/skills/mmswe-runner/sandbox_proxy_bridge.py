#!/usr/bin/env python3
"""
sandbox_proxy_bridge.py — expose the VM-loopback anonymizer proxy to docker containers.

Problem: the anonymizer proxy that holds the anonymized key listens on the VM's 127.0.0.1
(e.g. 127.0.0.1:8091, Claude format). Harbor runs the Tier-3 rubric judge INSIDE a docker
container, whose 127.0.0.1 is its own loopback — so the judge can't reach the proxy and fails
with "Connection error". The key is fine; it's a container->host-loopback networking gap.

Fix (mirrors tb-trial-runner v2): the docker bridge gateway (default 172.17.0.1) is an address
the container CAN reach that routes back to the VM. Nothing listens there by default, so this
script runs a plain TCP forwarder that listens on that gateway and relays every connection to the
VM's 127.0.0.1:<proxy>. The caller then points the in-container ANTHROPIC_BASE_URL at
http://<gateway>:<listen-port> and the request lands on the proxy.

Binds 0.0.0.0 by default (so it's reachable from any docker network's gateway, not just the
default bridge) but advertises the gateway IP the container should dial. Preflights the upstream
first and prints one of:
    BRIDGE_READY http://<gateway>:<port>
    BRIDGE_UPSTREAM_DOWN <reason>
Runs until killed (SIGINT/SIGTERM). Pure stdlib.
"""
import argparse, socket, sys, threading, signal

def relay(src, dst):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try: s.shutdown(socket.SHUT_RDWR)
            except OSError: pass

def handle(client, up_host, up_port):
    try:
        upstream = socket.create_connection((up_host, up_port), timeout=30)
    except OSError as e:
        try: client.close()
        except OSError: pass
        sys.stderr.write(f"[bridge] upstream connect failed: {e}\n")
        return
    t = threading.Thread(target=relay, args=(client, upstream), daemon=True)
    t.start()
    relay(upstream, client)

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
                    help="the gateway IP the container should dial (advertised in BRIDGE_READY)")
    args = ap.parse_args()

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
    print(f"BRIDGE_READY http://{args.gateway}:{port}", flush=True)
    sys.stderr.write(f"[bridge] {args.listen_host}:{port} -> {args.upstream_host}:{args.upstream_port} "
                     f"(container dials http://{args.gateway}:{port})\n")

    def shutdown(*_):
        try: srv.close()
        except OSError: pass
        sys.exit(0)
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while True:
        try:
            client, _ = srv.accept()
        except OSError:
            break
        threading.Thread(target=handle,
                         args=(client, args.upstream_host, args.upstream_port),
                         daemon=True).start()

if __name__ == "__main__":
    main()
