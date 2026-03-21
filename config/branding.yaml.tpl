# Branding — Fenótipo do agente
# Cada agente tem o seu. Genótipo (código) lê este arquivo.
# Se não encontrar, usa defaults neutros.

agent_name: "{{AGENT_NAME}}"
org_name: "{{ORG_NAME}}"
org_short: "{{ORG_SHORT}}"
logo_filename: "logo.svg"
css_var_prefix: "brand"

# Cores primárias (CSS custom properties)
colors:
  primary: "#2b6cb0"
  green: "#38a169"
  yellow: "#ed8936"
  web_blue: "#2b6cb0"
  web_blue_dark: "#1a365d"
  logo_blue: "#2b6cb0"

# Blog
blog:
  port: {{BLOG_PORT}}
  host: "127.0.0.1"
  auth_enabled: {{BLOG_AUTH_ENABLED}}
  auth_user: "{{BLOG_AUTH_USER}}"
  auth_pass: "{{BLOG_AUTH_PASS}}"

# Paths
memory_project_dir: "{{MEMORY_PROJECT_DIR}}"
skill_prefix: "{{SKILL_PREFIX}}"
