# Tarefas do Teams na agenda (Power Automate)

O inatel-sync não lê o Teams direto: a API de tarefas do Teams (Education) exige permissão de administrador
do Inatel. O caminho que funciona com a sua conta de aluno é um fluxo do **Power Automate** que reage ao
e-mail que o Teams manda quando o professor publica uma tarefa.

> Funciona se o Inatel liberar o Power Automate para alunos (entre em https://make.powerautomate.com com
> a conta @inatel.br; se abrir, está liberado). Os nomes dos campos podem mudar um pouco com o tempo.

## O que o fluxo faz

Chegou e-mail do Teams sobre tarefa nova → cria uma tarefa no seu **Google Tasks** (lista "Teams"), com o
assunto do e-mail como título e o link da tarefa nas notas. A data de entrega fica no texto do e-mail; o
Google Tasks mostra a tarefa e você ajusta a data se quiser lembrete no dia certo.

## Passo a passo

1. Abra https://make.powerautomate.com com a conta **@inatel.br**.
2. **Criar** → **Fluxo da nuvem automatizado**. Nome: `Teams para Google Tasks`.
3. Gatilho: **Quando um novo email chegar (V3)** (Office 365 Outlook). Em *Mostrar opções avançadas*:
   - **De**: `noreply@email.teams.microsoft.com`
   - **Filtro de assunto**: `tarefa` (se o seu Teams estiver em inglês: `assignment`)
   - **Pasta**: Caixa de Entrada
4. **+ Nova etapa** → procure **Google Tasks** → **Criar uma tarefa** (ou *Create a task*).
   - Ao conectar, entre com a sua conta **Gmail pessoal** (a mesma do inatel-sync).
   - **Lista de tarefas**: escolha ou crie `Teams` antes no Google Tasks.
   - **Título**: conteúdo dinâmico **Assunto**.
   - **Notas**: conteúdo dinâmico **Visualização do corpo** (traz o nome da turma e o prazo).
   - **Data de conclusão**: deixe vazio, ou use a expressão `utcNow()` para cair no dia em que chegou.
5. **Salvar**. Para testar, use **Testar → Manualmente** e espere o próximo e-mail de tarefa (ou reencaminhe
   um antigo para você mesmo com o mesmo assunto).

## Dicas

- Se o Teams não manda e-mail de tarefa: no Teams, **Configurações → Notificações → E-mail** e ative as
  notificações de *Tarefas*.
- Quer na agenda em vez do Tasks? Troque a etapa 4 por **Google Agenda → Criar um evento (V3)**, agenda
  `Inatel - Aulas e Provas`, evento de dia inteiro. Fica fora do controle do inatel-sync (ele nunca apaga
  eventos que não criou).
- Para desligar: abra o fluxo no Power Automate e clique em **Desativar**.
