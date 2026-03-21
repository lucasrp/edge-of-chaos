#!/usr/bin/env python3
"""
Gera relatorio HTML autocontido com branding do agente (lido de branding.yaml).

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
Branding (logo, org name, cores) vem de ~/edge/config/branding.yaml.
"""

import argparse
import sys
from pathlib import Path
from datetime import date

# Load branding from config
sys.path.insert(0, str(Path(__file__).parent.parent / "config"))
try:
    from branding import load_branding
    _BRAND = load_branding()
except Exception:
    _BRAND = {"agent_name": "agent", "org_name": "", "logo_filename": "", "org_short": ""}


def main():
    parser = argparse.ArgumentParser(description="Gera relatorio HTML com branding do agente")
    parser.add_argument("--title", default=None, help="Titulo do relatorio")
    parser.add_argument("--subtitle", default=None, help="Subtitulo (aparece no header)")
    parser.add_argument("--content", default=None, help="Arquivo HTML com conteudo do <main>")
    parser.add_argument("--yaml", default=None, help="YAML spec (alternativa a --content)")
    parser.add_argument("--output", required=True, help="Caminho do HTML de saida")
    parser.add_argument("--date", default=None, help="Data no footer (DD/MM/YYYY). Default: hoje")
    parser.add_argument("--no-branding", action="store_true", help="Omite logo e footer institucional")
    args = parser.parse_args()

    # Validar: precisa de --content ou --yaml
    if not args.content and not args.yaml:
        parser.error("--content ou --yaml e obrigatorio")
    if args.content and args.yaml:
        parser.error("use --content ou --yaml, nao ambos")

    # Paths dos assets (relativos a este script)
    script_dir = Path(__file__).parent
    css_path = script_dir / "assets" / "base.css"
    logo_file = _BRAND.get("logo_filename", "")
    svg_path = script_dir / "assets" / logo_file if logo_file else None

    # Ler assets
    css = css_path.read_text(encoding="utf-8")
    svg = svg_path.read_text(encoding="utf-8") if svg_path and svg_path.exists() else ""

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
        org_name = _BRAND.get("org_name", "")
        org_line = f'<p>{org_name}</p>' if org_name else ""
        footer_html = f"""  <footer class="report-footer">
    <div class="footer-content">
      {org_line}
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
        yaml_src = Path(args.yaml).resolve()
        yaml_dst = yaml_dest.resolve()
        if yaml_src != yaml_dst:
            shutil.copy2(args.yaml, yaml_dest)
        print(f"Relatorio gerado: {output_path} ({output_path.stat().st_size / 1024:.1f}KB) + {yaml_dest.name} ({yaml_dest.stat().st_size / 1024:.1f}KB)")
    else:
        print(f"Relatorio gerado: {output_path} ({output_path.stat().st_size / 1024:.1f}KB)")


if __name__ == "__main__":
    main()
