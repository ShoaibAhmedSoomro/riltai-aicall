"""The hostnames nginx answers for, and the certificate that has to match them.

`PUBLIC_HOST_ALIASES` exists for domain cutovers. Inbound telephony numbers
carry a callback URL configured inside the *provider's* console — Twilio's,
Telnyx's, Plivo's — which this deployment cannot see or rewrite. So the moment
`PUBLIC_HOST` changes, every inbound number still pointing at the old hostname
gets a `server_name` miss. Serving both names makes the cutover non-breaking.

Two failure modes are worth a test rather than review:

1. **A name nginx serves with no matching SAN** is a browser certificate error,
   and **a SAN nginx does not serve** is a wasted renewal. `rilt_public_host_names`
   is the single source for both nginx's `server_name` and certbot's `-d` flags
   precisely so they cannot drift — so the test asserts they come from it.

2. **The value is substituted straight into nginx.conf.** An alias containing
   `;` or `}` renders a config that fails to parse, which takes the site down on
   the *next restart* rather than at edit time. Validation has to reject it.

Runs the real function out of `scripts/lib/setup_common.sh` rather than a copy,
for the same reason `test_container_drain.py` extracts the real heredoc: a copy
can drift from what ships.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parents[2] / "scripts" / "lib" / "setup_common.sh"
TEMPLATE = (
    Path(__file__).resolve().parents[2]
    / "deploy"
    / "templates"
    / "nginx.remote.conf.template"
)

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None, reason="needs bash to run the real shell function"
)


def _host_names(public_host, aliases=None):
    """Call the real rilt_public_host_names, returning (rc, stdout, stderr)."""
    env_lines = f"PUBLIC_HOST={_q(public_host)}\n"
    if aliases is not None:
        env_lines += f"PUBLIC_HOST_ALIASES={_q(aliases)}\n"
    script = f"""
        set -uo pipefail
        {env_lines}
        . '{LIB.as_posix()}'
        rilt_public_host_names
    """
    r = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, timeout=60
    )
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def _q(value):
    return "'" + value.replace("'", "'\\''") + "'"


def test_a_plain_install_answers_for_one_name():
    rc, out, _ = _host_names("voice.example.com")
    assert rc == 0
    assert out == "voice.example.com"


def test_unset_aliases_change_nothing():
    # The overwhelmingly common case: the key is absent from .env entirely.
    rc, out, _ = _host_names("voice.example.com", aliases=None)
    assert rc == 0
    assert out == "voice.example.com"


def test_the_canonical_host_comes_first():
    """Order is load-bearing, not cosmetic.

    The render preflight reads the FIRST name off the server_name line and
    requires it to equal PUBLIC_HOST, so an alias sorted ahead of the canonical
    host fails the deploy.
    """
    rc, out, _ = _host_names("new.example.com", "old.example.com")
    assert rc == 0
    assert out.split()[0] == "new.example.com"
    assert out.split() == ["new.example.com", "old.example.com"]


def test_several_aliases_are_all_kept():
    rc, out, _ = _host_names("new.example.com", "a.example.com b.example.com")
    assert rc == 0
    assert out.split() == ["new.example.com", "a.example.com", "b.example.com"]


def test_an_alias_repeating_the_canonical_host_is_dropped():
    # nginx rejects a duplicated server_name outright, and it is an easy thing
    # to leave behind after a cutover finishes.
    rc, out, _ = _host_names("voice.example.com", "voice.example.com")
    assert rc == 0
    assert out == "voice.example.com"


@pytest.mark.parametrize(
    "bad",
    [
        "evil;}server{listen 80",  # closes the block and opens another
        "-leading-dash.example.com",
        "trailing-dash-.example.com",
        "under_score.example.com",
        "has/slash.example.com",
        "semi;colon",
        "brace}",
    ],
)
def test_an_alias_that_would_corrupt_nginx_conf_is_refused(bad):
    """Refused loudly at render time rather than at the next nginx restart."""
    rc, out, err = _host_names("voice.example.com", bad)
    assert rc != 0, f"accepted {bad!r} and would have written it into nginx.conf"
    assert "invalid hostname" in err.lower()
    assert bad not in out


def test_the_field_is_space_separated_not_a_single_hostname():
    """A space is a separator here, not a typo to reject.

    Worth pinning because it is the one place the validation looks too lax: a
    value with a space in it is accepted, and correctly so -- it becomes two
    names. Anything that made a space invalid would break multi-alias setups.
    """
    rc, out, _ = _host_names("new.example.com", "old.example.com legacy.example.com")
    assert rc == 0
    assert out.split() == [
        "new.example.com",
        "old.example.com",
        "legacy.example.com",
    ]


def test_the_sslip_hostname_this_deployment_uses_is_accepted():
    # Digits-and-dashes labels are legal and this deployment's previous host was
    # exactly that shape, so an over-strict regex would refuse the real alias.
    rc, out, _ = _host_names("aicall.rilt.ai", "145-241-126-226.sslip.io")
    assert rc == 0
    assert out.split() == ["aicall.rilt.ai", "145-241-126-226.sslip.io"]


def test_every_server_name_in_the_template_gets_the_full_list():
    """Both the :80 and :443 blocks must carry every name.

    The ACME challenge is served from the :80 block. If only :443 learned the
    alias, renewal for the old hostname would fail once its challenge stopped
    matching -- months later, silently, as an expiry.
    """
    names = "aicall.rilt.ai 145-241-126-226.sslip.io"
    script = f"""
        set -uo pipefail
        PUBLIC_HOST=aicall.rilt.ai
        PUBLIC_HOST_ALIASES='145-241-126-226.sslip.io'
        FASTAPI_WORKERS=1
        . '{LIB.as_posix()}'
        rilt_render_remote_nginx_conf '{TEMPLATE.parents[2].as_posix()}' /dev/stdout
    """
    r = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, timeout=60
    )
    assert r.returncode == 0, r.stderr
    rendered = [line.strip() for line in r.stdout.splitlines() if "server_name" in line]
    assert len(rendered) == 2, f"expected a :80 and a :443 block, got {rendered}"
    for line in rendered:
        assert line == f"server_name {names};", line
