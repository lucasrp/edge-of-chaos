#!/usr/bin/env python3
"""
Generate self-contained HTML report.

Uso (HTML cru):
    python3 generate_report.py \
        --title "Titulo do Relatorio" \
        --subtitle "Subtitulo" \
        --content conteudo.html \
        --output ~/edge/reports/relatorio.html

Uso (YAML spec):
    python3 generate_report.py \
        --yaml spec.yaml \
        --output ~/edge/reports/relatorio.html

Com --yaml, title/subtitle/date sao extraidos do YAML (podem ser sobrescritos via CLI).
O script cuida de: CSS (base.css), SVG logo, header, footer, faixa tricolor.
"""

import argparse
import sys
from pathlib import Path
from datetime import date


def main():
    parser = argparse.ArgumentParser(description="Gera report HTML")
    parser.add_argument("--title", default=None, help="Titulo do relatorio")
    parser.add_argument("--subtitle", default=None, help="Subtitulo (aparece no header)")
    parser.add_argument("--content", default=None, help="Arquivo HTML com conteudo do <main>")
    parser.add_argument("--yaml", default=None, help="YAML spec (alternativa a --content)")
    parser.add_argument("--output", required=True, help="Caminho do HTML de saida")
    parser.add_argument("--date", default=None, help="Data no footer (DD/MM/YYYY). Default: hoje")
    parser.add_argument("--no-branding", action="store_true", help="Skip institutional branding")
    args = parser.parse_args()

    # Validar: precisa de --content ou --yaml
    if not args.content and not args.yaml:
        parser.error("--content ou --yaml e obrigatorio")
    if args.content and args.yaml:
        parser.error("use --content ou --yaml, nao ambos")

    # Paths dos assets (relativos a este script)
    script_dir = Path(__file__).parent
    css_path = script_dir / "assets" / "base.css"
    svg_path = script_dir / "assets" / "logo.svg"

    # Ler assets
    css = css_path.read_text(encoding="utf-8")
    svg = svg_path.read_text(encoding="utf-8")

    # Ler conteudo: YAML ou HTML cru
    if args.yaml:
        from yaml_to_html import yaml_to_html, load_spec, get_validation_error_count
        content = yaml_to_html(args.yaml)
        n_errors = get_validation_error_count()
        if n_errors > 0:
            print(f"\nBLOQUEADO: {n_errors} erro(s) de validacao. Corrija o YAML e tente novamente.", file=sys.stderr)
            sys.exit(1)
        spec = load_spec(args.yaml)
        # Extrair title/subtitle/date do YAML se nao vieram via CLI
        if not args.title:
            args.title = spec.get("title", "Relatorio")
        if not args.subtitle:
            args.subtitle = spec.get("subtitle", "")
        if not args.date:
            args.date = spec.get("date")
        if spec.get("no_branding"):
            args.no_branding = True
    else:
        content_path = Path(args.content)
        content = content_path.read_text(encoding="utf-8")

    # Validar title (obrigatorio)
    if not args.title:
        parser.error("--title e obrigatorio quando usando --content")

    # Data
    if args.date:
        footer_date = args.date
    else:
        today = date.today()
        footer_date = today.strftime("%d/%m/%Y")

    # Subtitle HTML
    subtitle_html = ""
    if args.subtitle and args.subtitle.strip():
        subtitle_html = f'<p class="subtitle">{args.subtitle}</p>'

    # Montar HTML
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
      <p class="footer-date">Gerado em {footer_date}</p>
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
      <p>edge-of-chaos</p>
      <p class="footer-date">Gerado em {footer_date}</p>
    </div>
  </footer>"""

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
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

    # Escrever output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")

    # Copiar YAML spec junto do HTML (para releitura eficiente — YAML e ~54% menor)
    if args.yaml:
        import shutil
        yaml_dest = output_path.with_suffix(".yaml")
        shutil.copy2(args.yaml, yaml_dest)
        print(f"Relatorio gerado: {output_path} ({output_path.stat().st_size / 1024:.1f}KB) + {yaml_dest.name} ({yaml_dest.stat().st_size / 1024:.1f}KB)")
    else:
        print(f"Relatorio gerado: {output_path} ({output_path.stat().st_size / 1024:.1f}KB)")


if __name__ == "__main__":
    main()
