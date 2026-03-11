# Continuum

Runtime local-first para Claude Code: memória persistente, rotinas autônomas e bootstrap inteligente via scanner de transcripts.

## Estrutura do projeto

```
continuum/
  pyproject.toml
  README.md
  LICENSE
  src/continuum/
    __init__.py          # version
    cli.py               # click CLI (init, scan, run, status, doctor, skills)
    config.py            # Config loading from continuum.toml
    init.py              # Bootstrap logic (interactive prompts, dir creation)
    scanner/
      __init__.py
      discover.py        # Find .jsonl transcripts
      parser.py          # Parse JSONL into Session objects
      heuristics.py      # Extract preferences, corrections, tech stack
      sanitize.py        # Remove sensitive data (3 modes)
      bootstrap.py       # Write bootstrap memory files
    skills/
      __init__.py
      manifest.py        # Skill dataclass from skill.yaml
      runner.py          # Execute skills
      scaffold.py        # `skills new` scaffolding
    memory/
      __init__.py
      writer.py          # Write memory files
      reader.py          # Read memory files
    templates/
      CLAUDE.md.template # Template for generated CLAUDE.md
      continuum.toml.template
    builtin_skills/
      consolidate-state/
        skill.yaml
        prompt.md
      daily-reflection/
        skill.yaml
        prompt.md
      project-discovery/
        skill.yaml
        prompt.md
  tests/
    test_e2e.py
    fixtures/
      sample_transcript.jsonl
```

## Convenções

- Python 3.10+, click para CLI
- Sem deps pesadas (sem Flask, sem ML, sem DB)
- Deps mínimas: click, pyyaml (para skill.yaml)
- tomllib stdlib (3.11+) para ler TOML, fallback para tomli
- Testes com pytest
- Código limpo, sem overengineering
- Cada módulo faz UMA coisa

## Onboarding flow (continuum init)

1. Perguntar nome do projeto (default: dirname)
2. Perguntar diretório de trabalho (default: cwd)
3. Perguntar domínio de trabalho (ex: "marketing", "pesquisa", "auditoria")
4. Perguntar idioma (default: en)
5. Detectar conta GitHub disponível (`gh auth status` ou `git config user.name`)
6. Perguntar skill prefix (default: cx)
7. Oferecer scan de transcripts existentes
8. Criar estrutura .continuum/
9. Se scan aceito, rodar pipeline discover→parse→heuristics→sanitize→bootstrap

## Scanner de transcripts

O scanner lê ~/.claude/projects/*/conversations/*.jsonl (ou paths similares).
Cada linha JSONL tem formato do Claude Code:
- Mensagens do tipo "human" e "assistant"
- Tool calls aninhados em content blocks
- Arquivos mencionados, comandos shell, etc.

Extrair:
- Preferências explícitas (idioma, verbosidade, estilo)
- Correções do usuário (padrões de negação após resposta)
- Stack tecnológico (linguagens, frameworks, tools)
- Padrões de projeto (dirs comuns, configs)
- Tópicos recorrentes (por frequência)

## Como rodar

```bash
pip install -e .
continuum --help
continuum init
continuum scan
continuum doctor
continuum status
continuum run consolidate-state
continuum skills list
continuum skills new my-skill
```
