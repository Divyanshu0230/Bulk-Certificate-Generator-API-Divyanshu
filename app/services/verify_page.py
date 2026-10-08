from html import escape

from app.schemas import Verification


def verification_page(verification: Verification) -> str:
    detail_row = ""
    if verification.detail:
        detail_row = _row("Detail", verification.detail)
    body = f"""
      <p class="mark">Valid certificate</p>
      <h1>{escape(verification.recipient_name)}</h1>
      <p class="lede">{escape(verification.description)}</p>
      <p class="event">{escape(verification.event_title)}</p>
      <dl>
        {_row("Issuer", verification.issuer)}
        {_row("Issue date", _format_date(verification))}
        {_row("Certificate number", verification.certificate_number)}
        {detail_row}
      </dl>
    """
    return _layout("Certificate verified", body)


def not_found_page() -> str:
    body = """
      <p class="mark invalid">Not found</p>
      <h1>This certificate number is not valid</h1>
      <p class="lede">Check the number printed on the certificate and try again.</p>
    """
    return _layout("Certificate not found", body)


def _format_date(verification: Verification) -> str:
    value = verification.issue_date
    return f"{value.day} {value.strftime('%B')} {value.year}"


def _row(label: str, value: str) -> str:
    return f"<div><dt>{escape(label)}</dt><dd>{escape(value)}</dd></div>"


def _layout(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --cream: #fbf7ef;
      --navy: #1b3a4b;
      --gold: #b8956a;
      --ink: #1c1917;
      --muted: #57534e;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: var(--cream);
      color: var(--ink);
      font-family: Palatino, "Palatino Linotype", Georgia, serif;
    }}
    main {{
      width: min(640px, calc(100% - 32px));
      margin: 32px 0;
      padding: 40px 36px;
      background: white;
      border: 1px solid var(--gold);
      box-shadow: 0 0 0 6px var(--cream), 0 0 0 7px var(--navy);
    }}
    .mark {{
      margin: 0;
      color: var(--navy);
      font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
      font-size: 12px;
      letter-spacing: 0.16em;
      text-transform: uppercase;
    }}
    .mark.invalid {{ color: #8a3b2d; }}
    h1 {{
      margin: 14px 0 8px;
      font-weight: 600;
      font-size: 36px;
      line-height: 1.15;
    }}
    .lede, .event {{ margin: 0; color: var(--muted); }}
    .event {{
      margin-top: 8px;
      color: var(--navy);
      font-size: 20px;
    }}
    dl {{ margin: 28px 0 0; }}
    dl div {{
      display: grid;
      grid-template-columns: 160px 1fr;
      gap: 12px;
      padding: 10px 0;
      border-top: 1px solid #eadfce;
    }}
    dt {{
      font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
      font-size: 12px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
    }}
    dd {{ margin: 0; }}
    @media (max-width: 560px) {{
      main {{ padding: 28px 20px; }}
      h1 {{ font-size: 30px; }}
      dl div {{ grid-template-columns: 1fr; gap: 4px; }}
    }}
  </style>
</head>
<body>
  <main>
    {body}
  </main>
</body>
</html>
"""
