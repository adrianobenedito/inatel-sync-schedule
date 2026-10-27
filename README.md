# inatel-sync

Mantém o seu **Google Agenda** atualizado sozinho com:

- **Portal Inatel**: calendário de provas e quadro de aulas da semana (feriados nacionais pulados);
- **Moodle** e **Moodle Code**: prazos de entrega e questionários;
- **Outlook** do computador (opcional): reuniões do trabalho numa agenda separada.

Cada parte é opcional. Roda escondido pelo Agendador do Windows, nunca duplica eventos e só mexe nos eventos
que ele mesmo criou. Tarefas do Teams: veja [docs/teams-power-automate.md](inatel_sync/docs/teams-power-automate.md).

## Instalar (Windows 10/11, sem admin)

1. Baixe `inatel-sync-<versão>.zip`, clique com o botão direito → **Extrair tudo**.
2. Abra a pasta extraída e dê dois cliques em **install.cmd**.
   - Se o Windows mostrar "O Windows protegeu o computador": **Mais informações → Executar assim mesmo**.
3. Responda o assistente. Ele vai:
   - listar os cursos do portal para você escolher e testar o seu login (a senha fica no Gerenciador de
     Credenciais do Windows, criptografada; nunca em arquivo);
   - ensinar a copiar o link do calendário do Moodle;
   - abrir o navegador para autorizar o Google Agenda. Vai aparecer **"O Google não verificou este app"**:
     é esperado (projeto de aluno). Clique em **Avançado → Acessar (não seguro)**. Use o Gmail pessoal;
   - mostrar uma simulação da primeira sincronização e só aplicar se você confirmar.

Precisa de internet na instalação (baixa o Python e as bibliotecas para `%LOCALAPPDATA%\inatel-sync`).

## Usar

```
inatel-sync status       o que rodou, quando roda de novo
inatel-sync run          sincroniza agora (ou: run portal | moodle | outlook)
inatel-sync run --dry-run   mostra o que mudaria, sem alterar nada
inatel-sync doctor       diagnóstico
inatel-sync setup        muda as respostas
inatel-sync auth         autoriza o Google de novo
inatel-sync config senha     senha do portal mudou
inatel-sync agenda add --titulo "..." --inicio "2026-11-10 14:00"    compromisso avulso
inatel-sync tarefas add --titulo "..." --data 2026-11-08             Google Tasks
```

Usa o Claude (Claude Code)? O assistente instala uma skill para você pedir "sincroniza minha agenda" ou
"marca na agenda" em português.

## Atualizar e desinstalar

- **Atualizar**: extraia o zip novo e rode o `install.cmd` dele. A configuração é mantida.
- **Desinstalar**: `%LOCALAPPDATA%\inatel-sync\uninstall.cmd`. Remove tarefas, senhas guardadas e o
  programa; os eventos que já estão na agenda ficam. Para tirar o acesso do Google:
  https://myaccount.google.com/permissions

## Segurança

- Pede só **Google Agenda** e **Google Tasks**. Nada de e-mail, Drive ou contatos.
- Senha do portal, link do Moodle e autorização do Google ficam no Gerenciador de Credenciais do Windows.
- Trava contra apagar em massa: se uma sincronização quiser remover mais de 5 eventos e mais de 30% dos que
  ela gerencia, não remove nada e avisa (`inatel-sync run <modulo> --forcar` depois de conferir).
- Só eventos futuros são removidos; o passado fica como está.
- Dados e logs: `%APPDATA%\inatel-sync` (`logs\sync.log`).

## Desenvolvimento

```
uv sync
uv run pytest
uv run python scripts/build.py          # dist/inatel-sync-<versao>.zip (precisa de instalador/client_secret.json)
uv run python scripts/build.py --teste  # build/...-teste.zip, sem client_secret, para testar a instalacao
```

Integrações extras podem ser plugins locais em `%APPDATA%\inatel-sync\plugins\*.py` exportando
`INTEGRACAO` (subclasse de `inatel_sync.integracoes.base.Integracao`), com uma seção própria no
`config.toml`. Plugins nunca entram no pacote.
