# Survival Policy

Saúde do sistema precede trabalho do operador.

## Regra principal

Toda sessão autônoma começa lendo `health/current.json`.

## Modos operacionais

| Modo | Score | Comportamento |
|------|-------|---------------|
| **normal** | >= 70 | Trabalho normal + 1 ação de remediação (content/quality) |
| **degraded** | 40-69 | Reparo + trabalho limitado (--max-turns reduzido) |
| **maintenance** | < 40 | Só diagnóstico + reparo + alerta ao operador |

## Hard-fails (forçam maintenance independente do score)

- `fs_rw = fail` (filesystem não escreve)
- `disk = critical` (< 2% livre)
- `sqlite = critical` (0 bytes ou corrompido)
- `git = fail` (repo inválido)

## Regras

1. Se `critical` ou `unhealthy`: NÃO executar tarefas normais antes de diagnosticar e tentar reparar
2. Se `degraded`: reservar parte da sessão para reparo
3. Nunca declarar sucesso sem artefato verificável (`*.ok`, JSON, curl 200, sqlite check)
4. Em falha parcial: tornar explícita, registrar incidente, degradar graciosamente
5. Se reparo falhar após tentativa: criar `health/operator-alert.flag` e informar operador
6. Saúde é derivada de evidência local (scripts shell), não de autoavaliação

## O que ler no bootstrap

```
health/current.json     → estado atual (score, status, componentes)
health/mode             → normal | degraded | maintenance
SURVIVAL_POLICY.md      → este arquivo
```
