# edge — leia antes de instalar

## Contrato deste derivado

Este repositório é **Hermes-only**. Toda orientação, delegação e revisão acontece em Hermes,
com subagentes independentes quando o contrato pedir separação de contexto. Não configure
superfícies de execução ou revisores externos.

## Clone fresco

Este repositório é **genótipo sem identidade**: `agent.yaml` não deve existir no clone.
Cada instalação o escreve como SAÍDA do onboarding; não o fabrique e não use o caminho
legado de apply.

Antes de qualquer bootstrap, estabeleça um perfil Hermes dedicado ao install:

```sh
export HERMES_HOME="$HOME/.hermes/profiles/edge"
```

O caminho é apenas um exemplo confirmável com o operador. Requisitos obrigatórios:

- `HERMES_HOME` deve estar definido e apontar para um perfil dedicado;
- nunca use o home global `~/.hermes` como destino de provisionamento;
- clone, install home e `HERMES_HOME` são árvores distintas;
- Hermes é o primary;
- não configure adversarial externo;
- ingestão de sessões fica dark até existir reader Hermes-native verificado;
- runtime do grafo fica dark no onboarding;
- heartbeat fica **off**; operação é manual-only até heartbeat Hermes-native.

Siga `skills/onboard/SKILL.md`. O bootstrap suportado recebe explicitamente
`--primary hermes --hermes-home "$HERMES_HOME"`. O finish não recebe
`--enable-heartbeat`.

Como reconhecer: se `state/bootstrap.json` não existe e ninguém declarou este diretório
como install vivo, trate-o como clone fresco e inicie pelo rito guiado.

## Install vivo

Preserve o perfil dedicado e as fronteiras dark declaradas. Para operação normal,
`CONTEXT.md` é o mapa, `CONTRACT.md` é o contrato e `docs/adr/` registra as decisões.
Nenhuma ausência de capacidade autoriza fallback para outra superfície ou store.
