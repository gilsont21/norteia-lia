"""Dados de exemplo, só para ver como a interface fica preenchida."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from .core import Servico


def popular(svc: Servico) -> None:
    faculdade = svc.criar_projeto("Faculdade", "#f5a623")
    trabalho = svc.criar_projeto("Trabalho", "#f0524a")
    casa = svc.criar_projeto("Casa", "#4dd0b1")
    pessoal = svc.criar_projeto("Projetos pessoais", "#4772fa")

    def nova(texto, projeto=None, dias=None, notas=""):
        t = svc.adicionar_rapido(texto, projeto_id=projeto.id if projeto else None)
        if dias is not None:
            t.prazo = date.today() + timedelta(days=dias)
        t.notas = notas
        return svc.salvar(t)

    nova("Entregar relatório de Estruturas de Arquivos !3 #si601", faculdade, -1,
         "Revisar a parte de índices e anexar o código.")
    prova = nova("Estudar para a prova de Estruturas de Arquivos !3 #si601", faculdade, 0)
    for passo in ("Rever índices e árvores B", "Refazer os exercícios da lista", "Resumir hashing"):
        svc.adicionar_subtarefa(prova.id, passo)
    svc.alternar_conclusao(svc.subtarefas(prova.id)[0].id)
    nova("Reunião de alinhamento da LIA !2 #lia", faculdade, 0)
    nova("Atualizar painel de processos !2 #automacao", trabalho, 0)
    nova("Revisar prompts do assistente interno #ia", trabalho, 1)
    nova("Responder e-mails pendentes", trabalho, 0)
    nova("Comprar legumes e frutas #mercado", casa, 0)
    nova("Pagar conta de luz !1 #contas", casa, 3)
    nova("Montar o protótipo do app de tarefas !2 #python", pessoal, 2)
    nova("Treino de pernas #saude", None, 1)
    nova("Ler artigo sobre engenharia de dados #estudo", None, 5)
    nova("Planejar viagem de intercâmbio", None, 20)
    nova("Ideias para o canal", None, None)
    nova("Academia todo dia às 7h #saude", None, 0)
    nova("Reunião semanal do time toda semana às 10h #trabalho", trabalho, 0)
    nova("Aula de Estruturas de Arquivos às 19h30 !2 #si601", faculdade, 0)
    svc.criar_filtro("Urgentes", {"prazo": "hoje", "prioridade_min": 2})
    svc.criar_filtro("Faculdade sem data", {"projeto_id": faculdade.id, "prazo": "sem"})
    feita = nova("Enviar currículo atualizado", trabalho, -2)
    feita.concluida_em = datetime.now() - timedelta(hours=3)
    svc.salvar(feita)
    feita2 = nova("Fazer backup dos arquivos", casa, -1)
    feita2.concluida_em = datetime.now() - timedelta(days=1)
    svc.salvar(feita2)

    # recursos da etapa 6: fixar, subtarefas em níveis, lista arquivada, etiqueta colorida, lembrete constante
    antigo = svc.criar_projeto("Intercâmbio 2025", "#b57edc")
    nova("Entregar relatório final do intercâmbio", antigo, None)
    svc.arquivar_projeto(antigo.id)
    svc.definir_cor_tag("si601", "#f5a623")
    svc.definir_cor_tag("lia", "#4dd0b1")
    svc.alternar_fixada(prova.id)
    sub = svc.subtarefas(prova.id)[1]
    svc.adicionar_subtarefa(sub.id, "Lista 3, questões 1 a 5")
    svc.adicionar_subtarefa(sub.id, "Lista 3, questões 6 a 10")
    reuniao = nova("Reunião com a orientadora às 15h !3", faculdade, 0)
    reuniao.insistir_min = 10
    svc.salvar(reuniao)

    # recursos das etapas 7 e 8: calendário, quadros, foco, hábitos, contagem
    from datetime import time

    from .core.foco import Sessao
    hoje = date.today()
    for titulo, dias, hora, dur, proj in (
            ("Aula de Estruturas de Arquivos", 0, time(19, 30), 120, faculdade),
            ("Reunião semanal do time", 1, time(10, 0), 60, trabalho),
            ("Dentista", 2, time(8, 30), 45, None),
            ("Almoço com a família", 3, time(12, 30), 90, casa),
            ("Orientação do TCC", -1, time(15, 0), 60, faculdade)):
        t = svc.adicionar_rapido(titulo, projeto_id=proj.id if proj else None)
        t.prazo, t.prazo_hora, t.duracao_min = hoje + timedelta(days=dias), hora, dur
        t.lembretes = [15]
        svc.salvar(t)
    longa = svc.adicionar_rapido("Escrever artigo da LIA", projeto_id=pessoal.id)
    longa.inicio, longa.prazo = hoje - timedelta(days=1), hoje + timedelta(days=5)
    svc.salvar(longa)
    semestre = svc.adicionar_rapido("Projeto final de Estruturas de Arquivos", projeto_id=faculdade.id)
    semestre.inicio, semestre.prazo = hoje + timedelta(days=2), hoje + timedelta(days=12)
    semestre.prioridade = type(semestre.prioridade)(3)
    svc.salvar(semestre)
    for nome in ("A fazer", "Em andamento", "Revisão"):
        svc.banco.definir_secoes(pessoal.id, svc.banco.secoes_da_lista(pessoal.id) + [nome])
    for t in svc.listar(pessoal.id):
        t.secao = "Em andamento" if "protótipo" in t.titulo else "A fazer"
        svc.salvar(t)
    svc.comentarios.adicionar(prova.id, "Perguntar ao professor se entra hashing extensível.")
    svc.modelos.salvar_de_tarefa(prova.id, "Semana de prova")

    agua = svc.habitos.criar("Beber água", "#4dd0b1", meta=8, unidade="copos", inicio=hoje - timedelta(days=30),
                           secao="Manhã")
    treino = svc.habitos.criar("Treinar", "#f5a623", dias=[0, 2, 4], inicio=hoje - timedelta(days=30),
                            secao="Tarde")
    for i in range(1, 25):
        if (hoje - timedelta(days=i)).weekday() in (0, 2, 4) and i % 5:
            svc.habitos.definir_quantidade(treino, hoje - timedelta(days=i), 1)
    leitura = svc.habitos.criar("Ler 20 minutos", "#b57edc", inicio=hoje - timedelta(days=30),
                              secao="Noite")
    for i in range(1, 12):
        d = hoje - timedelta(days=i)
        if i not in (4, 9):
            svc.habitos.definir_quantidade(leitura, d, 1)
        svc.habitos.definir_quantidade(agua, d, 8 if i % 3 else 5)
    svc.habitos.definir_quantidade(agua, hoje, 3)
    for i in range(10):
        d = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0) - timedelta(days=i)
        svc.foco.registrar(Sessao(d, 25 * 60 * (1 + i % 3), tarefa_uuid=prova.uuid))
    svc.contagens_regressivas.criar("Prova de Estruturas de Arquivos", hoje + timedelta(days=9), "#f0524a")
    svc.contagens_regressivas.criar("Viagem de intercâmbio", hoje + timedelta(days=118), "#4772fa")
    svc.contagens_regressivas.criar("Aniversário da mãe", date(1970, (hoje + timedelta(days=40)).month,
                                                              (hoje + timedelta(days=40)).day), "#4dd0b1", anual=True)
