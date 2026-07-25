# edge — leia antes de instalar

## Se este é um clone fresco (você ainda não é um install)

O `agent.yaml` rastreado neste repositório é a **identidade do host canônico**, não a sua.
Um clone NUNCA vira install aplicando esse arquivo:

- **NÃO** rode `edge-apply --yaml agent.yaml` — essa é a estrada legada para um fenótipo
  que JÁ pertence a este host.
- **SIM**: siga o rito guiado em `skills/onboard/SKILL.md` — entreviste o operador
  (nome, pasta, CLIs, adversarial, segredos/embeddings, dias de backfill com cheque de
  custo), conduza a instalação inteira explicando cada passo e emende no primeiro mentor.
  `agent.yaml` é a SAÍDA do onboarding, nunca a semente.

Como saber: se `state/bootstrap.json` não existe e ninguém te disse que este diretório é
um install vivo, trate como clone fresco e pergunte primeiro.

## Se este é um install vivo

Operação normal — `CONTEXT.md` é o mapa, `CONTRACT.md` o contrato, `docs/adr/` as
decisões.
