"""One layout for every transactional email, plus its plain-text twin.

Why a module and not an f-string per message: the first two emails (password
reset, invitation) each hand-built their HTML, which is how you end up with two
different-looking products and, worse, two different answers to "is the
inviter's name escaped?". Everything user-controlled goes through `_e()` here,
once.

Email clients are not browsers. The layout is deliberately boring:

  * Tables and inline styles. Outlook renders with Word's engine; flexbox, grid
    and <style>-only rules do not survive it.
  * A "bulletproof" button -- a bordered table cell around a plain link -- so
    the button is still a button when the client strips background images and
    padding on <a>.
  * No remote images. Many clients block them by default, and a wordmark that
    needs a fetch renders as a broken-image box on first open. The brand is
    text.
  * The link is printed in full under the button. Corporate mail scanners and
    some clients rewrite or disable buttons, and a reset link you cannot copy is
    a locked-out user.
  * A plain-text part. Without one, spam filters score the message down and
    text-only clients show raw HTML.
  * Dark mode via prefers-color-scheme, honoured by Apple Mail and most mobile
    clients; others simply keep the light palette, which is why the light
    palette is the one set inline.

The palette is the product's own: neutral greys, chroma 0, one near-black
accent. No brand colour is introduced just for mail.
"""

from dataclasses import dataclass
from html import escape
from urllib.parse import urlparse

BRAND = "AICall"

# Inline = what every client shows. Dark overrides live in the <style> block and
# use !important because inline styles would otherwise win.
_BG = "#f4f4f5"
_CARD = "#ffffff"
_INK = "#18181b"
_MUTED = "#52525b"
_RULE = "#e4e4e7"


@dataclass(frozen=True)
class EmailContent:
    html: str
    text: str


def _e(value: str) -> str:
    """Escape for both text nodes and double-quoted attributes."""
    return escape(value, quote=True)


def _safe_url(url: str) -> str:
    """Refuse anything that is not http(s).

    A link in an email is clicked by someone who trusts the sender. A
    `javascript:` or `data:` URL here would be an injection that arrives from
    the product's own domain, so this fails loudly instead of rendering it.
    """
    if urlparse(url).scheme not in ("http", "https"):
        raise ValueError(f"Refusing to put a non-http(s) URL in an email: {url!r}")
    return url


def render_email(
    *,
    preheader: str,
    heading: str,
    paragraphs: list[str],
    cta_label: str | None = None,
    cta_url: str | None = None,
    footnote: str | None = None,
) -> EmailContent:
    """Build the HTML and plain-text bodies from the same inputs.

    Both are produced from one set of arguments so they cannot drift: the text
    part is not an afterthought that forgets the link.
    """
    if bool(cta_label) != bool(cta_url):
        raise ValueError("cta_label and cta_url go together")
    url = _safe_url(cta_url) if cta_url else None

    body_html = "".join(
        f'<p style="margin:0 0 16px;font-size:16px;line-height:24px;color:{_INK};" '
        f'class="ink">{_e(p)}</p>'
        for p in paragraphs
    )

    button_html = ""
    if url:
        button_html = f"""
<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:24px 0 8px;">
  <tr>
    <td align="center" bgcolor="{_INK}" class="btn" style="border-radius:8px;">
      <a href="{_e(url)}" target="_blank"
         style="display:inline-block;padding:13px 28px;font-size:16px;font-weight:600;line-height:20px;color:#ffffff;text-decoration:none;border-radius:8px;"
         class="btn-link">{_e(cta_label or "")}</a>
    </td>
  </tr>
</table>
<p style="margin:16px 0 0;font-size:13px;line-height:20px;color:{_MUTED};" class="muted">
  Button not working? Copy this address into your browser:<br>
  <a href="{_e(url)}" target="_blank" style="color:{_MUTED};word-break:break-all;" class="muted">{_e(url)}</a>
</p>"""

    footnote_html = ""
    if footnote:
        footnote_html = (
            f'<p style="margin:24px 0 0;padding-top:16px;border-top:1px solid {_RULE};'
            f'font-size:13px;line-height:20px;color:{_MUTED};" class="muted rule">'
            f"{_e(footnote)}</p>"
        )

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="supported-color-schemes" content="light dark">
<title>{_e(heading)}</title>
<style>
  @media (prefers-color-scheme: dark) {{
    .bg {{ background-color:#09090b !important; }}
    .card {{ background-color:#18181b !important; }}
    .ink {{ color:#fafafa !important; }}
    .muted {{ color:#a1a1aa !important; }}
    .rule {{ border-color:#3f3f46 !important; }}
    .btn {{ background-color:#fafafa !important; }}
    .btn-link {{ color:#18181b !important; }}
  }}
  @media only screen and (max-width:620px) {{
    .wrap {{ width:100% !important; }}
    .pad {{ padding:24px !important; }}
  }}
</style>
</head>
<body class="bg" style="margin:0;padding:0;background-color:{_BG};">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">{_e(preheader)}&#847;&zwnj;&nbsp;&#847;&zwnj;&nbsp;&#847;&zwnj;&nbsp;</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" class="bg" bgcolor="{_BG}" style="background-color:{_BG};">
  <tr>
    <td align="center" style="padding:32px 16px;">
      <table role="presentation" width="560" cellpadding="0" cellspacing="0" border="0" class="wrap" style="width:560px;max-width:560px;">
        <tr>
          <td style="padding:0 0 16px 4px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;font-size:18px;font-weight:700;letter-spacing:-0.01em;color:{_INK};" class="ink">{BRAND}</td>
        </tr>
        <tr>
          <td class="card pad" bgcolor="{_CARD}" style="background-color:{_CARD};border:1px solid {_RULE};border-radius:12px;padding:36px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
            <h1 style="margin:0 0 20px;font-size:24px;line-height:30px;font-weight:700;letter-spacing:-0.02em;color:{_INK};" class="ink">{_e(heading)}</h1>
            {body_html}
            {button_html}
            {footnote_html}
          </td>
        </tr>
        <tr>
          <td style="padding:20px 4px 0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;font-size:12px;line-height:18px;color:{_MUTED};" class="muted">
            You received this because of activity on a {BRAND} account. If that wasn&rsquo;t you, you can ignore this message.
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
</body>
</html>"""

    text_parts = [heading, "", *[p for p in paragraphs]]
    if url:
        text_parts += ["", f"{cta_label}:", url]
    if footnote:
        text_parts += ["", "--", footnote]
    text_parts += ["", f"-- {BRAND}"]

    return EmailContent(html=html, text="\n".join(text_parts))
