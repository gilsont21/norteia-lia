# Guia: conectar o Google Calendar ao app Tarefas

O app conversa com o Google Calendar pela API oficial. Para isso o Google exige que você tenha o seu próprio
"projeto" gratuito (leva uns 5 minutos, uma vez só). O acesso fica só no seu computador: a autorização é guardada no
cofre do Windows (ou, se não houver, no banco local) e nunca vai para o servidor de sincronização.

## 1. Criar o projeto e ativar a API
1. Entre em https://console.cloud.google.com/ com a conta Google que você quer usar.
2. No topo, clique no seletor de projetos › **Novo projeto**. Nome: `Tarefas`. Criar.
3. Menu **APIs e serviços › Biblioteca**. Procure **Google Calendar API** › **Ativar**.

## 2. Tela de permissão (OAuth)
1. **APIs e serviços › Tela de permissão OAuth** (ou "Google Auth Platform").
2. Tipo de usuário: **Externo**. Nome do app: `Tarefas`. E-mail de suporte e de contato: o seu.
3. Escopos: pode pular (o app pede o acesso na hora do login).
4. Usuários de teste: adicione o seu e-mail (necessário enquanto o app estiver em "Teste").
5. **Importante:** clique em **Publicar app** (status "Em produção"). Enquanto o app fica em "Teste", o Google
   cancela a autorização a cada 7 dias e você teria que entrar de novo toda semana. Não precisa pedir verificação:
   o app é só seu.

## 3. Criar as credenciais
1. **APIs e serviços › Credenciais › Criar credenciais › ID do cliente OAuth**.
2. Tipo de aplicativo: **App para computador** (Desktop app). Nome: `Tarefas PC`.
3. Copie o **ID do cliente** e a **Chave secreta do cliente**.

## 4. Conectar no app
1. No app: engrenagem › **Integrações (Google Calendar)...** › **Google Calendar**.
2. Cole o ID e a chave secreta e clique em **Conectar com o Google**.
3. O navegador abre. Escolha a conta. O Google mostra "O Google não verificou este app": clique em
   **Avançado › Acessar Tarefas (não seguro)**. É normal, o app é seu. Aceite o acesso ao Google Agenda.
4. Volte ao app. Marque os calendários que quer ver (todos começam desmarcados) e, se quiser, **Enviar minhas
   tarefas com data para o Google Calendar**.

## Como funciona depois
- **Google → app:** os eventos dos calendários marcados aparecem no calendário do app (somente leitura). Botão
  direito num evento: "Criar tarefa a partir deste evento" ou "Abrir no Google Calendar".
- **App → Google:** tarefas com data viram eventos num calendário chamado **Tarefas**. Tarefa sem hora vira evento de
  dia inteiro; os lembretes da tarefa viram lembretes do evento. Tarefa concluída aparece com "✓" no título.
- **Edição nos dois sentidos (calendário "Tarefas"):** mudar data/hora/título do evento no Google muda a tarefa; mudar
  a tarefa muda o evento. Em conflito vale a edição mais recente. Criar um evento no calendário "Tarefas" cria uma
  tarefa. Apagar o evento no Google **não** apaga a tarefa.
- A sincronização roda ao abrir o app, a cada 5 minutos e no botão **Sincronizar agora**.

## Problemas comuns
- **"O Google pediu para você entrar de novo":** botão **Entrar de novo** na tela do Google.
- **"Não devolveu a autorização permanente":** remova o acesso do app em https://myaccount.google.com/permissions e
  conecte de novo.
- **Login vence a cada 7 dias:** o app ficou em "Teste". Volte à tela de permissão OAuth e clique em **Publicar app**.
- Para sair: **Desconectar** (remove do app os calendários e as ligações; os eventos que já estão no Google ficam lá).

> Observação: estes passos descrevem o console do Google como ele costuma ser; os nomes dos menus podem mudar um
> pouco. Se algo não bater, o princípio é o mesmo: ativar a Calendar API, criar um ID de cliente do tipo "App para
> computador" e publicar a tela de permissão.
