# Features — o que está ligado/desligado
# "auto" = detecta se o secret correspondente existe. true/false = override.
# Editável pelo operador. O agente lê mas não escreve.

review:
  adversarial: auto         # edge-consult — review por outro modelo (precisa: OPENAI_API_KEY)
  review_gate: auto         # LLM-as-judge no pipeline de publicação (precisa: OPENAI_API_KEY)

search:
  exa: auto                 # busca semântica via Exa (precisa: EXA_API_KEY)

research:
  deep: auto                # edge-deepresearch — research profunda com web (precisa: OPENAI + GOOGLE)
  adversarial: auto         # cross-provider validation com convergência (precisa: 2+ LLM providers)

notifications:
  # Notification channels are NOT hardcoded here. Agents that need
  # Slack, Telegram, or other messaging create their own primitives
  # via libexec/ — same as any other external source. The install
  # is indifferent to which channels the operator chooses.
  # See: docs/TOOL_CONTRACT.md, skills/_shared/required-context.md

git:
  auto_push: false          # push autônomo após commits — opt-in explícito (precisa: GITHUB_PAT)
  auto_pr: false            # criar PRs automaticamente — opt-in explícito (precisa: GITHUB_PAT)

blog:
  auth: auto                # autenticação básica no dashboard (precisa: BLOG_AUTH_USER/PASS)
  public: false             # expor dashboard na rede (0.0.0.0) — opt-in explícito, default localhost

heartbeat:
  enabled: true             # ciclo autônomo ativo por padrão
  interval: "{{ SYSTEMD_INTERVAL }}"
                            # Heartbeat inativo NÃO é erro — é escolha válida do operador.
