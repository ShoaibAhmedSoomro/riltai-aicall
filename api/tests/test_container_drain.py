"""The container entrypoint's drain, exercised against a stub worker.

scripts/start_services_docker.sh waits for in-flight calls to finish before it
SIGTERMs the uvicorns, because uvicorn force-closes live call WebSockets on
SIGTERM and would otherwise cut every conversation mid-sentence on each deploy.

That logic is embedded as a python heredoc inside the shell script (deliberately:
api/Dockerfile COPYs a fixed list of seven scripts, so a separate file could be
left out of the image and the drain would then skip silently). To avoid testing
a copy that can drift from what ships, this extracts the heredoc from the real
script and runs THAT.

The failure this guards against is specific and expensive: a drain that reports
"nothing in flight" while calls are live is worse than no drain at all, because
it makes cutting them look deliberate.
"""

import http.server
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "start_services_docker.sh"


def drain_source() -> str:
    """The python block the shipped entrypoint actually runs."""
    # newline="" then normalise: the file is CRLF in a Windows checkout and LF
    # in the image, and the heredoc must be found in both.
    text = SCRIPT.read_text(encoding="utf-8").replace("\r\n", "\n")
    # [^\n]* because the heredoc line carries a trailing `|| true`.
    m = re.search(r"<<'PY'[^\n]*\n(.*?)\nPY\n", text, re.S)
    assert m, "no python heredoc found in start_services_docker.sh"
    return m.group(1)


class _State:
    """Per-server stub state. A class attribute would be shared between the two
    servers in the consecutive-port test, which is the one test that has to tell
    them apart."""

    def __init__(self):
        self.counts = [0]      # popped left to right; the last value repeats
        self.status = 200


def _handler_for(state):
    class _Worker(http.server.BaseHTTPRequestHandler):
        """Stands in for one uvicorn's /health/active-calls."""

        def do_GET(self):  # noqa: N802 - stdlib signature
            if state.status != 200:
                self.send_error(state.status)
                return
            n = state.counts.pop(0) if len(state.counts) > 1 else (state.counts[0] if state.counts else 0)
            body = f'{{"active_calls":{n},"loop_lag_p95_ms":0,"loop_lag_max_ms":0}}'.encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):  # silence the test output
            pass

    return _Worker


def _serve(port, state):
    srv = http.server.HTTPServer(("127.0.0.1", port), _handler_for(state))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


@pytest.fixture
def worker():
    """One stub worker on an arbitrary free port; yields (port, state)."""
    state = _State()
    srv = _serve(0, state)
    try:
        yield srv.server_address[1], state
    finally:
        srv.shutdown()
        srv.server_close()


@pytest.fixture
def pair():
    """Two stub workers on CONSECUTIVE ports; yields (base, base_state, next_state).

    Consecutive because that is how the container lays workers out --
    UVICORN_BASE_PORT + i -- and the drain has to walk the same range.
    """
    import socket

    for _ in range(50):
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        base = probe.getsockname()[1]
        probe.close()
        try:
            s0, s1 = _State(), _State()
            a = _serve(base, s0)
            try:
                b = _serve(base + 1, s1)
            except OSError:
                a.shutdown(); a.server_close()
                continue
            try:
                yield base, s0, s1
            finally:
                for srv in (a, b):
                    srv.shutdown(); srv.server_close()
            return
        except OSError:
            continue
    pytest.skip("could not find two consecutive free ports")


def run_drain(port, workers=1, max_wait=6, interval=1, secret="s"):
    env = dict(os.environ, RILT_DEVOPS_SECRET=secret)
    # The stub is plain loopback HTTP; an inherited proxy would send the poll
    # somewhere else and every assertion here would be meaningless.
    env.pop("HTTP_PROXY", None)
    env.pop("http_proxy", None)
    env["NO_PROXY"] = "127.0.0.1,localhost"
    return subprocess.run(
        [sys.executable, "-c", drain_source(), str(port), str(workers), str(max_wait), str(interval)],
        capture_output=True, text=True, timeout=max_wait + 25, env=env,
    )


def test_returns_immediately_when_nothing_in_flight(worker):
    port, w = worker
    w.counts = [0]
    r = run_drain(port)
    assert r.returncode == 0, r.stderr
    assert "drained" in r.stdout, r.stdout


def test_waits_while_calls_are_live_then_drains(worker):
    port, w = worker
    w.counts = [2, 1, 0]           # busy, busy, then clear
    r = run_drain(port)
    # "call(s) in flight" only appears on the busy branch. Matching bare
    # "in flight" would also match the success line "drained: no calls in
    # flight", which let a mutant that always reported zero pass this test.
    assert "call(s) in flight" in r.stdout, r.stdout
    assert "drained" in r.stdout, r.stdout


def test_gives_up_after_max_wait_rather_than_hanging(worker):
    port, w = worker
    w.counts = [1]                 # never clears
    r = run_drain(port, max_wait=3)
    assert "timed out" in r.stdout, r.stdout
    assert r.returncode == 0, "must not fail the shutdown path"


def test_unreadable_worker_does_not_hang_the_deploy(worker):
    # 403/503 means the count cannot be read at all. Waiting the full timeout on
    # every single deploy would be worse than saying so and moving on.
    port, w = worker
    w.status = 403
    r = run_drain(port, max_wait=30)
    assert "skipping drain" in r.stdout, r.stdout
    # And it must not claim success on the way out. Falling through to
    # "drained: no calls in flight" would put a lie in the deploy log at exactly
    # the moment an operator most needs to know the drain did not happen.
    assert "drained" not in r.stdout, r.stdout


def test_a_port_with_no_listener_is_not_counted_as_busy():
    # A refused connection means no uvicorn is there, so it holds no calls.
    # Counting it as busy would stall every deploy for the full timeout when
    # FASTAPI_WORKERS is larger than the number of workers actually up.
    import socket

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    dead = s.getsockname()[1]
    s.close()                       # nothing is listening on `dead` now
    r = run_drain(dead, max_wait=4)
    assert "drained" in r.stdout, r.stdout


def test_a_worker_that_never_answers_counts_as_busy():
    """The asymmetry that keeps the drain honest.

    A refused connection means no listener, so that worker holds no calls ->
    idle. But a worker that accepts and then never answers is a live process we
    failed to read, and assuming it is idle would SIGTERM it mid-call. Unknown
    must mean busy; only 'definitely nothing there' means idle.
    """
    import socket

    hole = socket.socket()
    hole.bind(("127.0.0.1", 0))
    # A generous backlog: with listen(1) the queue fills on the first poll and
    # the next connect is refused, which flips the stub into the *other* case
    # mid-test and makes it flaky.
    hole.listen(50)                 # accepts the TCP connect, answers nothing
    port = hole.getsockname()[1]
    try:
        r = run_drain(port, max_wait=6)
        # The invariant is the classification, not the eventual outcome: an
        # unreadable worker must be counted as busy at least once. Treating it
        # as idle would print "drained" immediately with no busy line at all.
        assert "call(s) in flight" in r.stdout, (
            f"an unreadable worker was treated as idle:\n{r.stdout}"
        )
    finally:
        hole.close()


def test_polls_every_worker_port_not_just_the_base(pair):
    """The bug this exists for: draining on the base port alone.

    Compose runs FASTAPI_WORKERS uvicorns on consecutive ports inside one
    container, each holding its own count. A drain that polls only the base
    port reports zero while workers on 8001+ are still mid-call, and then
    SIGTERMs all of them -- cutting exactly the conversations it was added to
    protect, while logging that it drained cleanly.

    So: base is idle, base+1 is busy. Polling only base finds nothing to wait
    for and never prints the busy line.
    """
    base, idle, busy = pair
    idle.counts = [0]              # base port: nothing in flight
    busy.counts = [3, 3, 0]        # base+1: busy, busy, then clear
    r = run_drain(base, workers=2, max_wait=10)
    assert "call(s) in flight" in r.stdout, (
        f"drain did not notice the busy worker on {base + 1}:\n{r.stdout}"
    )
    assert "drained" in r.stdout, r.stdout
