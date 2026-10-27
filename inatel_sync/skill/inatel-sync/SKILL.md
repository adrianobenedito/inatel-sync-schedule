---
name: inatel-sync
description: Operar o inatel-sync, que mantém o Google Agenda do usuário atualizado com o Portal Inatel (provas e aulas), o Moodle e o Outlook — sincronizar agora, ver status, diagnosticar, reconfigurar — e marcar compromissos ou tarefas avulsas no Google Agenda/Google Tasks. Use quando o usuário disser "sincroniza minha agenda", "atualiza as provas", "o sync rodou?", "por que a agenda não atualizou", "marca na minha agenda", "adiciona uma tarefa", "quais tarefas eu tenho".
---

# inatel-sync

Comando `inatel-sync` (no PATH). Saída em português; código 0 = ok ou só aviso, 2 = precisa de ação do
usuário (a mensagem diz o comando), 1 = erro inesperado, 3 = sem internet.

## Sincronizar e conferir

| Pedido | Comando |
|---|---|
| sincronizar tudo agora | `inatel-sync run` |
| só um módulo | `inatel-sync run portal` / `moodle` / `outlook` |
| ver o que mudaria, sem alterar | `inatel-sync run --dry-run` |
| quando rodou / quando roda | `inatel-sync status` |
| algo parece errado | `inatel-sync doctor` |

- Rode `--dry-run` antes quando o usuário estiver em dúvida; linhas `+` entram, `~` mudam, `-` saem.
- "Trava de segurança" no log: o sync quis apagar muitos eventos e não apagou nada. Mostre ao usuário o
  dry-run e só rode `inatel-sync run <modulo> --forcar` se ele confirmar que está certo.
- "Rode: inatel-sync auth" → peça ao usuário para rodar (abre o navegador; ele precisa clicar).
- Senha do portal mudou → `inatel-sync config senha` (o usuário digita; nunca peça a senha no chat).
- Link do Moodle → `inatel-sync config moodle-url moodle` (ou `code`) com o link copiado.
- Mudar respostas (cores, horários, integrações) → `inatel-sync setup` (interativo: o usuário roda) ou
  `inatel-sync config set secao.chave valor` e depois `inatel-sync agendar`.

## Compromisso avulso no Google Agenda

```
inatel-sync agenda add --titulo "Reunião do TCC" --inicio "2026-11-10 14:00" --fim "2026-11-10 15:00" --lembrete 30
inatel-sync agenda add --titulo "Entrega relatório" --data 2026-11-12 --chave relatorio-tcc --agenda Inatel
inatel-sync agenda remove --chave relatorio-tcc --agenda Inatel
```

- `--data` = dia inteiro; `--inicio/--fim` = com horário (fim padrão: 1 h depois). `--ate` = último dia
  de um evento de vários dias. `--repetir` = semanal etc. `--cor` = nome da cor.
- Use `--chave` sempre que puder atualizar depois: rodar de novo com a mesma chave atualiza, não duplica.
- `--agenda`: `principal` (padrão), o nome de uma agenda (cria se não existir).
- Confirme data, hora e título com o usuário quando o pedido for ambíguo; use o fuso de São Paulo.

## Google Tasks

```
inatel-sync tarefas add --titulo "Estudar para P1 de calculo" --data 2026-11-08 --chave p1-calculo
inatel-sync tarefas list
inatel-sync tarefas done --chave p1-calculo
inatel-sync tarefas remove --chave p1-calculo
```

Compromisso com horário vai na agenda, não no Tasks.

## Não faça

- Não leia nem mostre `%APPDATA%\inatel-sync\estado.json`, o keyring ou links do Moodle (têm token pessoal).
- Não edite eventos com a tag `inatel-sync` à mão pela API: o próximo sync desfaz.
- Não use `--forcar` sem o usuário confirmar.
