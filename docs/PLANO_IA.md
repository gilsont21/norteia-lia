# Assistente de IA do app (plano e estado)

App da LIA, sem servidor: tudo roda no PC de cada membro e vai direto do app para o provedor de IA escolhido.

## O que foi combinado
- Um chat principal, com "Nova conversa" e histórico simples (nada de vários chats paralelos).
- A pessoa escolhe a IA: Gemini (padrão recomendado), Claude, ChatGPT ou DeepSeek, e cola a própria chave de API.
- A chave é guardada no cofre do sistema, aparece só na hora de colar e depois só mostra os 4 últimos caracteres.
  Dá para substituir ou apagar, nunca para ver de novo.
- Versão do modelo: um padrão por provedor, com campo "Modelo" em Avançado para trocar. Sem lista de modelos para manter.
- A IA não muda nada sozinha: ela propõe um plano, a pessoa clica em Aplicar, e dá para Desfazer.

## O que está feito (esta rodada)
| Parte | Onde | Estado |
|---|---|---|
| Provedores (Gemini, Claude, OpenAI, DeepSeek), formato neutro, ferramentas | `norteia/core/ia_provedores.py` | Feito, testado com IA simulada |
| Chave no cofre (`keyring`, reserva no banco local), máscara, apagar, fora do backup | `ConfigIA` | Feito |
| Assistente: contexto do dia, ferramentas de leitura e de escrita, plano, aplicar e desfazer | `norteia/core/assistente.py` | Feito |
| Conversas guardadas no aparelho | `Conversas`, tabela `conversa_ia` | Feito |
| Tela de configuração (IA, chave, testar conexão, modelo, privacidade, preferências) | `norteia/ui/pagina_ia.py` | Feito |
| Página de chat (ícone novo na barra, Ctrl+8) com sugestões rápidas e cartão do plano | `norteia/ui/pagina_ia.py` | Feito |
| Erros passageiros do provedor (500, 502, 503, 504): o app tenta 3 vezes, esperando 2 s e 5 s, e depois mostra uma mensagem clara em português | `ia_provedores.py` | Feito |
| Anexos no chat: imagem, PDF, Word e texto (clipe, arrastar, Ctrl+V; até 5; imagens grandes reduzidas) | `arquivos_ia.py`, `pagina_ia.py` | Feito, testado com IA simulada |
| Voz no chat: gravação do microfone, onda animada, transcrição pelo Gemini (áudio embutido), ChatGPT (gpt-transcribe) ou Groq (whisper-large-v3-turbo); a escolha de quem transcreve é separada da IA do chat | `voz.py`, `ia_provedores.transcrever` | Feito, testado com microfone simulado |
| "Sugerir subtarefas" usa a IA escolhida (e o caminho antigo do Claude continua valendo sem chave nova) | `janela.py` | Feito |

Ferramentas de leitura: tarefas por filtro, busca, agenda (inclui eventos do Google), listas e estatísticas (concluídas por
dia, por lista e por horário). Ferramentas de escrita (viram plano): criar, atualizar (inclui reagendar), concluir e apagar
tarefa, criar lista e guardar preferência.

## O que NÃO está feito
- Anexos e voz só foram testados com simulações: falta ensaiar com microfone real no Windows (confira em Configurações >
  Privacidade e segurança > Microfone se o app tem acesso) e com imagens reais em cada provedor.
- Voz só no Gemini, no ChatGPT e no Groq (que só serve para voz). Claude e DeepSeek não recebem áudio, mas dá para usar Claude ou DeepSeek no chat e Groq na voz. PDF no DeepSeek exige `pip install pypdf`.
- Arquivos além de imagem, PDF, Word e texto (planilhas, vídeo, áudio solto) ainda não.
- Plano do dia proativo (notificação de manhã) e revisão semanal automática. O chat já responde "planejar meu dia" e
  "analisar minha rotina" quando você pede.
- Painel lateral do chat dentro da lista de tarefas (hoje o chat é uma página própria).
- Lista de modelos vinda da API do provedor.
- Chamadas reais: tudo foi testado contra respostas simuladas no formato de cada provedor. Os nomes de modelo padrão
  foram conferidos nas páginas oficiais em 28/10/2026 (gemini-3.8-flash, claude-haiku-5-5, deepseek-flash,
  gpt-transcribe e whisper-large-v3-turbo para voz). O gpt-4o-mini do ChatGPT não foi reconferido e pode estar velho.
  Os nomes mudam com o tempo: o whisper-1 da OpenAI sai do ar em 26/02/2027. Se o "Testar
  conexão" disser que o modelo não foi encontrado, troque o nome em Avançado.

## Segurança e privacidade (limites honestos)
- O app precisa ler a chave para chamar a IA. Ela fica no Cofre de Credenciais do Windows (via `keyring`). Quem rodar código
  dentro da sua conta do Windows consegue lê-la. O que o app garante: não mostra, não registra em log, não exporta no
  backup e não envia ao servidor de sincronização.
- Sem `keyring` instalado, o app guarda a chave no banco local (texto simples). Por isso `keyring` entrou nos requisitos.
- O que você escreve, as tarefas e a agenda vão para o provedor escolhido. A tela de configuração avisa isso e tem a opção
  de não enviar o texto das notas. No Gemini gratuito o Google pode usar o conteúdo para melhorar os produtos dele.
- Recomende a cada membro criar a chave com limite de gasto quando o provedor permitir, e revogá-la no site se desconfiar.
- Claude e ChatGPT cobram por uso e a assinatura do chat não vale como chave. O Gemini tem camada gratuita com limites.

## Próximos passos sugeridos
1. Você testar com uma chave real do Gemini e me dizer o que a IA respondeu (principalmente se propõe reagendamentos bons).
2. Ajustar o texto de instruções da IA com base nisso.
3. Plano do dia proativo e revisão semanal.
4. Painel lateral do chat.
