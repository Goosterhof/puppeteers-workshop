#!/usr/bin/env python3
"""Side-port verify boot — the booth on 127.0.0.1:7901 for bench ratification.

The investor's foreground booth owns :7900 and is never killed mid-session;
this window exists so server changes can be probed live without touching it.
Run with the ComfyUI machine venv python (same substrate as start-prompter.sh).
"""
from http.server import ThreadingHTTPServer

import server

if __name__ == "__main__":
    print("side-port verify booth on http://127.0.0.1:7901", flush=True)
    ThreadingHTTPServer(("127.0.0.1", 7901), server.BoothWindow).serve_forever()
