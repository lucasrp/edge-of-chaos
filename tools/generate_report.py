#!/usr/bin/env python3
"""
Generate self-contained HTML report.

Usage (raw HTML):
    python3 generate_report.py \
        --title "Report Title" \
        --subtitle "Subtitle" \
        --content content.html \
        --output ~/edge/reports/report.html

Usage (YAML spec):
    python3 generate_report.py \
        --yaml spec.yaml \
        --output ~/edge/reports/report.html

With --yaml, title/subtitle/date are extracted from the YAML (can be overridden via CLI).
The script handles: CSS (base.css), SVG logo, header, footer, accent stripe.
"""

import argparse
import sys
from pathlib import Path
from datetime import date


def main():
    parser = argparse.ArgumentParser(description="Generate self-contained HTML report")
    parser.add_argument("--title", default=None, help="Report title")
    parser.add_argument("--subtitle", default=None, help="Subtitle (appears in header)")
    parser.add_argument("--content", default=None, help="HTML file with <main> content")
    parser.add_argument("--yaml", default=None, help="YAML spec (alternative to --content)")
    parser.add_argument("--output", required=True, help="Output HTML path")
    parser.add_argument("--date", default=None, help="Date in footer (YYYY-MM-DD). Default: today")
    parser.add_argument("--no-branding", action="store_true", help="Omit logo and institutional footer")
    args = parser.parse_args()

    # Validate: need --content or --yaml
    if not args.content and not args.yaml:
        parser.error("--content or --yaml is required")
    if args.content and args.yaml:
        parser.error("use --content or --yaml, not both")

    # Asset paths (relative to this script)
    script_dir = Path(__file__).parent
    css_path = script_dir / "assets" / "base.css"
    svg_path = script_dir / "assets" / "logo-horizontal.svg"

    # Read assets
    css = css_path.read_text(encoding="utf-8")
    svg = ""
    if svg_path.exists():
        svg = svg_path.read_text(encoding="utf-8")

    # Read content: YAML or raw HTML
    if args.yaml:
        from yaml_to_html import yaml_to_html, load_spec, get_validation_error_count
        content = yaml_to_html(args.yaml)
        n_errors = get_validation_error_count()
        if n_errors > 0:
            print(f"\nBLOCKED: {n_errors} validation error(s). Fix the YAML and try again.", file=sys.stderr)
            sys.exit(1)
        spec = load_spec(args.yaml)
        # Extract title/subtitle/date from YAML if not provided via CLI
        if not args.title:
            args.title = spec.get("title", "Report")
        if not args.subtitle:
            args.subtitle = spec.get("subtitle", "")
        if not args.date:
            args.date = spec.get("date")
        if spec.get("no_branding"):
            args.no_branding = True
    else:
        content_path = Path(args.content)
        content = content_path.read_text(encoding="utf-8")

    # Validate title (required)
    if not args.title:
        parser.error("--title is required when using --content")

    # Date
    if args.date:
        footer_date = args.date
    else:
        today = date.today()
        footer_date = today.strftime("%Y-%m-%d")

    # Subtitle HTML
    subtitle_html = ""
    if args.subtitle and args.subtitle.strip():
        subtitle_html = f'<p class="subtitle">{args.subtitle}</p>'

    # Build HTML
    no_branding = getattr(args, 'no_branding', False)

    if no_branding:
        header_html = f"""  <header class="report-header" style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);">
    <div class="header-content">
      <div class="header-text">
        <h1>{args.title}</h1>
        {subtitle_html}
      </div>
    </div>
    <div class="header-stripe"></div>
  </header>"""
        footer_html = f"""  <footer class="report-footer">
    <div class="footer-content">
      <p class="footer-date">Generated on {footer_date}</p>
    </div>
  </footer>"""
    else:
        header_html = f"""  <header class="report-header">
    <div class="header-content">
      <div class="logo">{svg}</div>
      <div class="header-text">
        <h1>{args.title}</h1>
        {subtitle_html}
      </div>
    </div>
    <div class="header-stripe"></div>
  </header>"""
        footer_html = f"""  <footer class="report-footer">
    <div class="footer-content">
      <p class="footer-date">Generated on {footer_date}</p>
    </div>
  </footer>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{args.title}</title>
  <style>
{css}
  </style>
</head>
<body>
{header_html}

  <main class="report-content">
{content}
  </main>

{footer_html}
</body>
</html>"""

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")

    # Copy YAML spec alongside HTML (for efficient re-reading -- YAML is ~54% smaller)
    if args.yaml:
        import shutil
        yaml_dest = output_path.with_suffix(".yaml")
        shutil.copy2(args.yaml, yaml_dest)
        print(f"Report generated: {output_path} ({output_path.stat().st_size / 1024:.1f}KB) + {yaml_dest.name} ({yaml_dest.stat().st_size / 1024:.1f}KB)")
    else:
        print(f"Report generated: {output_path} ({output_path.stat().st_size / 1024:.1f}KB)")


if __name__ == "__main__":
    main()
