# edge — leia antes de instalar

## Se este é um clone fresco (você ainda não é um install)

Este repositório é **genótipo sem identidade**: não existe `agent.yaml` aqui — cada host
escreve o seu como SAÍDA do onboarding (o arquivo é untracked/gitignored de propósito).

- **NÃO** fabrique um `agent.yaml` nem rode `edge-apply` — essa é a estrada legada para
  um fenótipo que JÁ pertence a um host vivo.
- **SIM**: siga o rito guiado em `skills/onboard/SKILL.md` — entreviste o operador
  (nome, pasta, CLIs, adversarial, segredos/embeddings, dias de backfill com cheque de
  custo), conduza a instalação inteira explicando cada passo e emende no primeiro mentor.
  `agent.yaml` é a SAÍDA do onboarding, nunca a semente.

Como saber: se `state/bootstrap.json` não existe e ninguém te disse que este diretório é
um install vivo, trate como clone fresco e pergunte primeiro.

## Se este é um install vivo

Operação normal — `CONTEXT.md` é o mapa, `CONTRACT.md` o contrato, `docs/adr/` as
decisões.
