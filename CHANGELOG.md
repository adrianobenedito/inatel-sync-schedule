# Changelog

## 2.0.0 - 2026-10-27

Reescrita como pacote instalável (`inatel_sync`), com um comando só.

### Novo
- Comando `inatel-sync`: `run [modulo|all] [--dry-run] [--forcar]`, `status`, `doctor`, `auth`, `setup`,
  `config`, `agendar`, `agenda`, `tarefas`, `desinstalar`.
- Instalador (`install.cmd` com uv embutido, sem admin) e assistente em português: escolha do curso pela
  lista do portal, teste do login, link do Moodle pela área de transferência, autorização do Google com o
  aviso de app não verificado, simulação antes da primeira sincronização.
- Uma tarefa do Agendador por integração (pasta `\inatel-sync`), sem janela, "executar assim que possível"
  e uma tarefa de logon (`run all`, 2 min de atraso).
- Motor de sincronização único e testado: lotes de 50, paginação, retry com backoff, só remove eventos
  futuros, trava contra remoção em massa (mais de 5 e mais de 30%).
- Configuração em TOML validada ao carregar; segredos só no keyring do Windows.
- Log rotativo (`logs\sync.log` + `debug.log`), sem URLs de OAuth nem tokens.
- Plugins locais em `%APPDATA%\inatel-sync\plugins`.
- Skill `inatel-sync` para o Claude Code.
- Guia do Power Automate para as tarefas do Teams.

### Corrigido
- Autorização do Google revogada/expirada vira mensagem clara ("Rode: inatel-sync auth") em vez de traceback.
- Sem internet: aviso de uma linha, nada alterado, código 0; a próxima execução recupera.
- Outlook: abre escondido com limite de 60 s; se não responder, pula com aviso.
- Moodle fora não impede o outro Moodle nem apaga eventos; calendário vazio não apaga nada.
- Execuções simultâneas não se atropelam (trava global).
- Feriados nacionais calculados (inclui Sexta-feira Santa), sem lista fixa por ano.

### Compatibilidade
- Eventos da versão 1 continuam reconhecidos (mesmas tags e chaves): a primeira sincronização com a 2.0
  não cria nem apaga nada que já estava certo.
- `inatel-sync config importar <pasta da v1>` migra config, ids das agendas e o token (para o keyring).
- `inatel-sync agendar --migrar-legado` troca as tarefas antigas pelas novas.
