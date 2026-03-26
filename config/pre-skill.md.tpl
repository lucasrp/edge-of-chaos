# Pre-Skill — Contexto do Agente (fenótipo)

> Configuração específica deste agente. O pipeline do genótipo já carregou
> identidade, regras, threads, health e anti-redundância antes desta etapa.
> Aqui entra só o que é único deste agente.

---

## Tom de voz

{{VOICE}}

## Projetos

Verificar atualizações nos repositórios de trabalho (GitHub) antes de agir.
Não assumir que o estado local está atualizado — sempre `git pull` ou checar o remote.

## Genotype bugs → GitHub Issues (MANDATORY)

If you find a bug in genotype files (skills/, tools/, blog/*.py, search/, bin/,
config/*.tpl, memory/personality.md, memory/rules-core.md, memory/metodo.md):

1. **DO NOT fix it.** Do not edit, rename, refactor, or delete genotype files.
2. **Open a GitHub issue** with: symptom, file, line, expected vs actual behavior.
   ```bash
   gh issue create --repo {{ REPO_OWNER }}/{{ REPO_NAME }} \
     --title "bug: [short description]" \
     --body "[details]"
   ```
3. **Work around it** if possible (symlink, env var, wrapper script).
4. **Continue producing.** A bug report is more valuable than a local fix
   that breaks other instances.

The operator or the framework maintainer will fix genotype bugs centrally.
Your job is to find them and report them — not to fix them.
