---
title: "workflow: atualizar edge-of-chaos no GitHub"
date: 2026-03-24
tags: [workflow, git, edge-of-chaos, deploy, genotype]
keywords: [edge-of-chaos, github, lucasrp, git push, repo sync, edge, edge-of-chaos repo, genotype propagation]
claims:
  - "~/edge/ e ~/edge-of-chaos/ sao repos independentes — mudancas no edge nao propagam automaticamente"
  - "secrets/ e gitignored no edge-of-chaos — MANIFEST.md so vive local"
secrets: []
cost_estimate: "$0"
---

## Trigger

Mudancas em arquivos genotype (skills, search, autonomy, config) que devem ser propagadas para o repo publico.

## Passos

1. Fazer as mudancas em `~/edge/` (repo de trabalho) e commitar normalmente
2. Copiar os arquivos alterados para `~/edge-of-chaos/`:
   ```bash
   cp ~/edge/<arquivo> ~/edge-of-chaos/<arquivo>
   ```
3. Verificar status:
   ```bash
   cd ~/edge-of-chaos && git status
   ```
4. Commitar e push:
   ```bash
   cd ~/edge-of-chaos && git add <arquivos> && git commit -m "mensagem" && git push origin main
   ```

## Secrets

Nenhum — push usa credenciais gh ja configuradas (lucasrp via HTTPS).

## Armadilhas

- `secrets/` e gitignored no edge-of-chaos. `git add secrets/MANIFEST.md` falha silenciosamente. Atualizar MANIFEST.md so localmente.
- `~/edge/` nao tem remote configurado — nao tentar `git push` la.
- Os dois repos tem historicos git independentes. Nao tentar merge/pull entre eles.

## Quando funciona

Sempre. Fluxo simples de cp + commit + push.

## Quando falha

Se o edge-of-chaos estiver dessincronizado (outro agente ou fork mandou push). Nesse caso, `git pull --rebase` antes.
