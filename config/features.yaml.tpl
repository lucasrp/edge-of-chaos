# Features — o que está ligado/desligado
# "auto" = detecta se o secret correspondente existe. true/false = override.
# Editável pelo operador. O agente lê mas não escreve.

review:
  adversarial: auto         # edge-consult — review por outro modelo (precisa: OPENAI_API_KEY)
  review_gate: auto         # LLM-as-judge no pipeline de publicação (precisa: OPENAI_API_KEY)

search:
  exa: auto                 # busca semântica via Exa (precisa: EXA_API_KEY)
  serper: auto              # busca web via Serper/Google (precisa: SERPER_API_KEY)

research:
  deep: auto                # edge-deepresearch — pesquisa profunda com web (precisa: OPENAI + GOOGLE)
  adversarial: auto         # cross-provider validation com convergência (precisa: 2+ LLM providers)

notifications:
  slack:
    enabled: auto           # auto = enabled if bot_token or webhook_url in secrets
    channels:
      heartbeat: ""         # Channel ID — onde o heartbeat reporta cada ciclo
      alerts: ""            # Channel ID — erros, health degraded, alertas críticos
      reports: ""           # Channel ID — entrega de relatórios HTML
      default: ""           # Channel ID — fallback para tudo que não tem canal específico
  telegram:
    enabled: auto           # auto = enabled if bot_token in secrets

git:
  auto_push: false          # push autônomo após commits — opt-in explícito (precisa: GITHUB_PAT)
  auto_pr: false            # criar PRs automaticamente — opt-in explícito (precisa: GITHUB_PAT)

blog:
  auth: auto                # autenticação básica no dashboard (precisa: BLOG_AUTH_USER/PASS)
  public: false             # expor dashboard na rede (0.0.0.0) — opt-in explícito, default localhost

heartbeat:
  enabled: true             # ciclo autônomo ativo
  interval: "{{ SYSTEMD_INTERVAL }}"
