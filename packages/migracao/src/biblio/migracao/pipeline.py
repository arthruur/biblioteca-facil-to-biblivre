"""
O pipeline de migração de ponta a ponta, sem terminal.

Os oito CLIs de `scripts/` continuam sendo a referência e continuam de pé.
Este módulo **não reimplementa nenhum deles**: chama as mesmas funções de
`biblio.legado` e `biblio.biblivre`, na mesma ordem, e acrescenta as três
coisas que a linha de comando não precisava ter.

1. **Relatório em dict, não em `print`.** O que o terminal imprimia entre um
   passo e outro era o ponto de decisão da pessoa. Numa tela isso tem de ser
   dado estruturado, senão não há como mostrar antes de gravar.

2. **Uma transação só para a migração inteira.** Os CLIs commitam por passo
   porque entre um e outro havia alguém lendo o relatório e decidindo. Aqui a
   decisão é tomada uma vez, na confirmação, e o que se promete é o que o
   README já promete do export: ou entra tudo, ou não entra nada. Isso é
   possível porque nenhum passo depende de commit do anterior — dentro da mesma
   transação o exemplar enxerga a obra recém-inserida (`mapa_por_035`), e a
   circulação enxerga exemplar e leitor. O reindex do BibLivre e o restart do
   Tomcat continuam sendo depois, e não são pré-requisito de passo nenhum
   (docs/IMPORTACAO_BIBLIVRE.md).

3. **O casamento dos passos em memória.** Na linha de comando o `holding_id` de
   um empréstimo vinha do `exemplares_mapa.csv` gerado pelo passo anterior.
   Aqui os mapas nascem do próprio plano; os CSVs continuam sendo escritos,
   mas como conferência e como ponte para uma execução parcial depois.

DUAS FASES, E A DIFERENÇA IMPORTA
---------------------------------
`analisar()` não abre transação e não escreve no banco: lê as tabelas do
`.bkp`, gera o MRC e o CSV de exemplares em disco e monta os planos de
leitores e circulação para contar o que aconteceria. Os números de casamento
(que exemplar acha a sua obra, que empréstimo acha o seu exemplar) saem de
mapas **provisórios**, porque as obras ainda não existem — as contagens e os
descartes são reais, os ids não. Nenhum id provisório vai para a tela.

`gravar()` refaz o casamento com os ids de verdade, dentro da transação. É por
isso que a conferência roda sem senha do Postgres e ainda assim diz quase tudo.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from pathlib import Path

from biblio.biblivre import acervo as _acervo
from biblio.biblivre import circulacao, exemplares, leitores, marc, obras
from biblio.biblivre.conexao import SCHEMA_PADRAO
from biblio.legado import bkp, tabela
from biblio.legado.consolidar import consolidar

# O que a execução deixa em disco. São os mesmos artefatos dos CLIs, com os
# mesmos nomes: quem quiser conferir no terminal, ou retomar a mão de onde a
# tela parou, encontra o que já conhece.
PASTA_TABELAS = "tabelas"
CONSOLIDADO = "acervo_consolidado.csv"
ARQ_MRC = "obras.mrc"
ARQ_EXEMPLARES = "exemplares.csv"
MAPA_EXEMPLARES = "exemplares_mapa.csv"
MAPA_LEITORES = "leitores_mapa.csv"

# As tabelas do Biblioteca Fácil que cada etapa precisa. Um `.bkp` truncado (ou
# de uma versão que não tenha alguma delas) tem de virar mensagem na tela antes
# de qualquer coisa, não KeyError no meio da consolidação.
TABELAS_POR_ETAPA = {
    "acervo": ("T09_ACER.dat", "T10_AUAC.dat", "T05_AUTO.dat", "T06_EDIT.dat",
               "T07_CLAS.dat", "T08_TIPO.dat", "T14_IDIO.dat"),
    "leitores": ("T04_LEIT.dat",),
    "circulacao": ("T13_MOVM.dat", "T11_MOVI.dat"),
}


@dataclass
class Opcoes:
    """
    O que a tela oferece de escolha, com os mesmos padrões dos CLIs.

    Os nomes são os das flags de `scripts/` — quem leu a documentação da linha
    de comando reconhece cada uma, e quem for depurar acha a origem.
    """

    # Etapas. Circulação depende de leitores e de exemplares, mas não obriga a
    # rodá-los agora: aceita os mapas de uma execução anterior (ver `_mapas`).
    acervo: bool = True
    leitores: bool = True
    circulacao: bool = True

    # Acervo
    incluir_excluidos: bool = False
    prefixo_tombo: str = ""
    ano_tombo: int | None = None
    biblioteca: str = ""
    tipo_aquisicao: str = exemplares.TIPO_AQUISICAO_MIGRACAO

    # Leitores
    campos_extras: str = "novos"
    offset_id: int = 0
    email_obrigatorio: bool = False

    # Circulação
    apenas_abertos: bool = False
    incluir_movimentacoes_excluidas: bool = False
    sem_reservas: bool = False
    reservas_desde: int = 2026

    # Gravação
    permitir_existentes: bool = False
    usuario: int = 1

    @classmethod
    def de_dict(cls, dados: dict | None) -> "Opcoes":
        """Ignora chave que a tela mandou e o pipeline não conhece."""
        validas = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in (dados or {}).items() if k in validas})

    def como_dict(self) -> dict:
        return asdict(self)

    def etapas(self) -> list[str]:
        return [e for e in ("acervo", "leitores", "circulacao")
                if getattr(self, e)]


def _nada(*_args, **_kwargs) -> None:
    """Progresso é opcional: fora do servidor ninguém está olhando."""


# --------------------------------------------------------------- extração

def extrair(origem, destino) -> dict:
    """
    `.bkp` -> pasta de tabelas. Devolve o inventário do que veio dentro.

    O `.bkp` é um container proprietário (docs/FORMATO_BKP.md); um arquivo que
    não é um deles sai daqui como erro claro, não como pasta vazia.
    """
    destino = Path(destino)
    tamanhos = bkp.extrair_para_pasta(str(origem), destino)
    if not tamanhos:
        raise ValueError(
            "Nenhuma tabela foi encontrada dentro do arquivo. Ele é mesmo um "
            "backup .bkp do Biblioteca Fácil?")
    return {"arquivos": tamanhos, "tabelas": inventario(destino)}


def inventario(pasta) -> list[dict]:
    """Uma linha por `.dat`: nome, descrição do próprio cabeçalho e registros."""
    return [
        {
            "arquivo": nome,
            "descricao": tab.descricao,
            "registros": tab.num_records,
            "campos": tab.num_fields,
            "layout_valido": tab.validar(),
        }
        for nome, tab in tabela.carregar_todas(pasta).items()
    ]


def tabelas_faltando(pasta, opcoes: "Opcoes") -> list[str]:
    pasta = Path(pasta)
    exigidas: list[str] = []
    for etapa in opcoes.etapas():
        exigidas.extend(TABELAS_POR_ETAPA[etapa])
    if opcoes.circulacao and not opcoes.sem_reservas:
        exigidas.append("T15_RESE.dat")
    return sorted({n for n in exigidas if not (pasta / n).exists()})


# ---------------------------------------------------------------- análise

def analisar(pasta, opcoes: "Opcoes", con=None, schema: str = SCHEMA_PADRAO,
             progresso=_nada) -> dict:
    """
    O relatório completo do que a gravação faria, sem escrever no banco.

    `con` é opcional: sem ele a conferência roda igual e o relatório diz o que
    ficou sem verificar — o mesmo princípio do dedup por ISBN, nunca degradar
    em silêncio. Com ele, acrescenta as contagens do destino, o prefixo de
    tombo real e os impedimentos que barrariam a gravação.
    """
    pasta = Path(pasta)
    tabelas_dir = pasta / PASTA_TABELAS

    rel: dict = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "opcoes": opcoes.como_dict(),
        "etapas": opcoes.etapas(),
        "acervo": None,
        "leitores": None,
        "circulacao": None,
        "destino": None,
        "avisos": [],
        "impedimentos": [],
    }

    faltam = tabelas_faltando(tabelas_dir, opcoes)
    if faltam:
        rel["impedimentos"].append(
            f"O backup não traz {', '.join(faltam)} — sem essas tabelas as "
            f"etapas escolhidas não têm o que ler.")
        return rel

    grupos: list[list[dict]] = []
    plano_leitores: dict | None = None

    if opcoes.acervo:
        progresso("consolidar", "cruzando acervo, autores, editoras e classificação")
        df = consolidar(tabelas_dir, opcoes.incluir_excluidos)
        df.to_csv(pasta / CONSOLIDADO, index=False, encoding="utf-8-sig")

        progresso("marc", "agrupando por obra e gerando o MARC21")
        linhas = marc.ler_csv_consolidado(pasta / CONSOLIDADO)
        grupos = marc.agrupar_por_obra(linhas)
        registros = [marc.montar_registro(g) for g in grupos]
        marc.escrever_mrc(registros, pasta / ARQ_MRC)
        total_ex = marc.escrever_csv_exemplares(grupos, pasta / ARQ_EXEMPLARES)

        # Sem 035 $a o exemplar não acha a sua obra depois. O CLI barra na hora
        # de gravar; aqui o impedimento já aparece na conferência.
        sem_035 = [i for i, r in enumerate(registros)
                   if not (r.get("035") and r["035"]["a"])]
        if sem_035:
            rel["impedimentos"].append(
                f"{len(sem_035)} registro(s) sem 035 $a — o casamento dos "
                f"exemplares depende dele.")

        tamanhos = [len(g) for g in grupos]
        rel["acervo"] = {
            "registros_origem": len(linhas),
            "obras": len(grupos),
            "exemplares": total_ex,
            "com_autor": int((df["autor_principal"] != "").sum()),
            "com_editora": int((df["editora"] != "").sum()),
            "com_isbn": int((df["isbn"] != "").sum()),
            "com_cdd": int((df["cdd"] != "").sum()),
            "obras_1_exemplar": sum(1 for t in tamanhos if t == 1),
            "obras_2_ou_mais": sum(1 for t in tamanhos if t > 1),
            "maior_grupo": max(tamanhos) if tamanhos else 0,
        }

    if opcoes.leitores:
        progresso("leitores", "montando usuários e campos personalizados")
        plano_leitores = _plano_de_leitores(tabelas_dir, opcoes)
        est = plano_leitores["estatisticas"]
        usuarios = plano_leitores["usuarios"]
        rel["leitores"] = {
            "total": len(usuarios),
            "ativos": est["ativos"],
            "inativos": est["inativos"],
            "valores": len(plano_leitores["valores"]),
            "id_inicial": usuarios[0][0] if usuarios else 0,
            "id_final": usuarios[-1][0] if usuarios else 0,
            "endereco_separado": est["endereco_separado"],
            "endereco_inteiro": est["endereco_inteiro"],
            "nascimentos_invalidos": len(plano_leitores["nascimentos_invalidos"]),
            "emails_estranhos": len(plano_leitores["emails_estranhos"]),
            "fotos_nao_migradas": est["fotos_nao_migradas"],
            "extras_descartados": est["extras_descartados"],
            "preenchimento": {k.split(":", 1)[1]: v
                              for k, v in sorted(est.items())
                              if k.startswith("campo:")},
        }

    if opcoes.circulacao:
        progresso("circulacao", "casando empréstimos com exemplares e leitores")
        rel["circulacao"] = _analisar_circulacao(
            pasta, tabelas_dir, opcoes, grupos, plano_leitores, con, schema, rel)

    if con is not None:
        progresso("destino", "conferindo o estado do BibLivre")
        rel["destino"] = _estado_do_destino(con, opcoes, schema, rel)
    else:
        rel["avisos"].append(
            "Sem conexão com o Postgres: as contagens do destino, o prefixo de "
            "tombo e a checagem de base ocupada não foram feitas.")

    return rel


def _plano_de_leitores(tabelas_dir, opcoes: "Opcoes") -> dict:
    """
    `T04_LEIT` -> plano de `users`/`users_values`, com a origem junto.

    `_origem` viaja com o plano porque o `user_id` de cada leitor só existe em
    relação ao `NUMLEITOR` da linha que o gerou — é isso que a circulação
    procura depois, e é isso que vai para o `leitores_mapa.csv`.
    """
    tab = tabela.carregar(tabelas_dir, "T04_LEIT.dat")
    linhas = list(tab.registros())
    plano = leitores.montar(linhas, opcoes.campos_extras, opcoes.offset_id)
    plano["_origem"] = linhas
    return plano


def _analisar_circulacao(pasta, tabelas_dir, opcoes, grupos, plano_leitores,
                         con, schema, rel) -> dict | None:
    """
    Empréstimos, multas e reservas com mapas provisórios.

    `circulacao.montar` só usa os mapas para *procurar* — o que ele devolve de
    contagem e de descarte é real. Os ids não são, e por isso nenhum deles sai
    daqui: o que vai para a tela é quanto entra, quanto fica de fora e por quê.
    """
    try:
        mapas = _mapas(pasta, opcoes, grupos, plano_leitores, con, schema,
                       provisorio=True)
    except (FileNotFoundError, ValueError) as e:
        rel["impedimentos"].append(str(e))
        return None

    tabelas_circ = circulacao.carregar_tabelas(tabelas_dir, opcoes.sem_reservas)
    plano = circulacao.montar(
        tabelas_circ["movm"], tabelas_circ["movi"], tabelas_circ["rese"],
        mapas["tombo_de"], mapas["record_de"], mapas["user_de"],
        mapas["holding_de"], id_base=mapas["id_base"],
        incluir_excluidos=opcoes.incluir_movimentacoes_excluidas,
        apenas_abertos=opcoes.apenas_abertos,
        reservas_desde=opcoes.reservas_desde)

    est = plano["estatisticas"]
    if plano["duplo_aberto"]:
        rel["impedimentos"].append(
            f"{len(plano['duplo_aberto'])} exemplar(es) com mais de um "
            f"empréstimo em aberto na origem. Resolva no Biblioteca Fácil antes "
            f"de carregar: duas linhas abertas para o mesmo exemplar deixam o "
            f"acervo incoerente, e a devolução resolveria só uma.")

    return {
        "movimentacoes_origem": len(tabelas_circ["movi"]),
        "emprestimos": len(plano["lendings"]),
        "abertos": est["abertos"],
        "devolvidos": est["devolvidos"],
        "multas": len(plano["multas"]),
        "reservas": len(plano["reservas"]),
        "excluidos_na_origem": est["excluidos"],
        "devolvidos_ignorados": est["devolvidos_ignorados"],
        "sem_data_emprestimo": est["sem_data_emprestimo"],
        "multas_canceladas": est["multas_canceladas"],
        "reservas_encerradas": est["reservas_encerradas"],
        "reservas_antigas": est["reservas_antigas"],
        "descartes": {motivo: len(itens)
                      for motivo, itens in plano["descartes"].items()},
        "por_ano": {k.split(":", 1)[1]: v for k, v in sorted(est.items())
                    if k.startswith("ano:")},
    }


def _estado_do_destino(con, opcoes: "Opcoes", schema: str, rel: dict) -> dict:
    """
    O que já existe no BibLivre — e o que disso barra a gravação.

    A migração é carga de base nova. Rodar sobre uma base povoada duplica
    acervo e colide ids, então base ocupada é impedimento por padrão; quem
    souber o que está fazendo marca "prosseguir com a base ocupada", que é o
    `--permitir-existentes` dos CLIs.
    """
    estado = {
        "obras": obras.contar_todos(con),
        "exemplares": exemplares.contar(con),
        "leitores": leitores.contar(con),
        **circulacao.contar(con),
    }

    with con.cursor() as cur:
        prefixo, origem = exemplares.ler_prefixo_tombo(cur, schema)
    estado["prefixo_tombo"] = opcoes.prefixo_tombo or prefixo
    estado["origem_prefixo"] = ("informado na tela" if opcoes.prefixo_tombo
                                else origem)

    if opcoes.leitores:
        estado["campos_a_criar"] = [c[0] for c in leitores.faltando(con)]

    ocupacoes = [
        (opcoes.acervo, estado["obras"], "registros bibliográficos em biblio_records"),
        (opcoes.acervo, estado["exemplares"], "exemplares em biblio_holdings"),
        (opcoes.leitores, estado["leitores"], "usuários em users"),
        (opcoes.circulacao, estado["emprestimos"], "empréstimos em lendings"),
    ]
    for ativa, quantos, onde in ocupacoes:
        if not ativa or not quantos:
            continue
        recado = f"Já existem {quantos:,} {onde}."
        if opcoes.permitir_existentes:
            rel["avisos"].append(recado + " Você marcou prosseguir mesmo assim.")
        else:
            rel["impedimentos"].append(
                recado + " A migração é uma carga de base nova: rodar por cima "
                "duplicaria o cadastro e os ids colidiriam. Apague os registros "
                "de teste ou marque 'prosseguir com a base ocupada'.")
    return estado


# ------------------------------------------------------------------ mapas

def _ler_exemplares(pasta) -> list[dict]:
    caminho = Path(pasta) / ARQ_EXEMPLARES
    if not caminho.exists():
        raise FileNotFoundError(
            f"{ARQ_EXEMPLARES} não existe nesta execução — rode a conferência "
            f"antes de gravar.")
    with open(caminho, encoding="utf-8-sig", newline="") as f:
        return [{k: (v or "") for k, v in r.items()} for r in csv.DictReader(f)]


def _mapas(pasta, opcoes: "Opcoes", grupos, plano_leitores, con, schema,
           provisorio: bool, plano_exemplares: dict | None = None) -> dict:
    """
    Os quatro mapas de que a circulação depende, venham de onde vierem.

    Na execução completa eles nascem dos planos desta mesma rodada. Numa
    execução parcial (só circulação, porque acervo e leitores já entraram
    antes) vêm dos CSVs de mapa que a rodada anterior deixou — os mesmos
    arquivos do `--mapa-out` dos CLIs.
    """
    pasta = Path(pasta)
    tombo_de: dict[int, str] = {}
    record_de: dict[int, int] = {}

    if opcoes.acervo:
        linhas_ex = _ler_exemplares(pasta)
        if plano_exemplares is not None:
            # Gravação: tombos e record_ids de verdade, já casados pelo 035 $a.
            for linha, tombo in zip(linhas_ex, plano_exemplares["tombos"]):
                num = int(linha["numacervo"])
                tombo_de[num] = tombo
                achado = plano_exemplares["mapa"].get(linha["id_origem"])
                if achado:
                    record_de[num] = achado[0]
        else:
            # Conferência: as obras ainda não existem. Os tombos saem do mesmo
            # gerador que a gravação usa (mesmo prefixo, mesmo contador) e os
            # record_ids são projetados — servem para contar, não para gravar.
            prefixo, contador = opcoes.prefixo_tombo or "Bib", None
            if con is not None:
                with con.cursor() as cur:
                    if not opcoes.prefixo_tombo:
                        prefixo, _ = exemplares.ler_prefixo_tombo(cur, schema)
                    contador, _ = exemplares.tombos_existentes(cur, prefixo)
            tombos, _, _ = exemplares.gerar_tombos(
                linhas_ex, prefixo, opcoes.ano_tombo, contador)

            ids = (obras.projetar_ids(con, len(grupos)) if con is not None
                   else list(range(1, len(grupos) + 1)))
            por_origem = {
                f"(BF){min(int(x['numacervo']) for x in grupo)}": rec_id
                for grupo, rec_id in zip(grupos, ids)
            }
            for linha, tombo in zip(linhas_ex, tombos):
                num = int(linha["numacervo"])
                tombo_de[num] = tombo
                if linha["id_origem"] in por_origem:
                    record_de[num] = por_origem[linha["id_origem"]]
    else:
        caminho = pasta / MAPA_EXEMPLARES
        tombo_de = circulacao.ler_mapa(caminho, "numacervo", "tombo",
                                       "mapa de exemplares")
        record_de = {k: int(v) for k, v in circulacao.ler_mapa(
            caminho, "numacervo", "record_id", "mapa de exemplares").items()}

    if opcoes.leitores and plano_leitores is not None:
        user_de = {int(origem["T04_NUMLEITOR"]): usuario[0]
                   for usuario, origem in zip(plano_leitores["usuarios"],
                                              plano_leitores["_origem"])}
    else:
        user_de = {k: int(v) for k, v in circulacao.ler_mapa(
            pasta / MAPA_LEITORES, "numleitor", "user_id",
            "mapa de leitores").items()}

    holding_de: dict[str, int] = {}
    id_base = 0
    if con is not None:
        ctx = circulacao.contexto_do_banco(con)
        holding_de = dict(ctx["holding_de"])
        id_base = ctx["id_base"]

    if provisorio:
        # Os exemplares desta rodada ainda não existem no banco. Id negativo
        # para que um vazamento apareça na hora, em vez de passar por id real.
        for i, tombo in enumerate(tombo_de.values(), start=1):
            holding_de.setdefault(tombo, -i)

    return {"tombo_de": tombo_de, "record_de": record_de, "user_de": user_de,
            "holding_de": holding_de, "id_base": id_base}


# --------------------------------------------------------------- gravação

def gravar(pasta, opcoes: "Opcoes", con, schema: str = SCHEMA_PADRAO,
           progresso=_nada) -> dict:
    """
    Executa a migração inteira numa transação. Commita no fim — ou nada entra.

    Espera que `analisar()` já tenha rodado nesta pasta: é dela que saem o
    `obras.mrc` e o `exemplares.csv`, que são exatamente os arquivos que os
    CLIs consomem. Reaproveitá-los é o que garante que o que foi conferido na
    tela é o que vai para o banco.
    """
    pasta = Path(pasta)
    tabelas_dir = pasta / PASTA_TABELAS

    resultado: dict = {
        "iniciado_em": datetime.now().isoformat(timespec="seconds"),
        "etapas": opcoes.etapas(),
        "obras": 0, "exemplares": 0, "leitores": 0, "valores": 0,
        "campos_criados": [], "emprestimos": 0, "multas": 0, "reservas": 0,
        "avisos": [], "proximos_passos": [],
    }

    plano_exemplares: dict | None = None
    plano_leitores: dict | None = None
    mapa_exemplares: list[tuple] = []

    try:
        if opcoes.acervo:
            progresso("obras", "inserindo registros bibliográficos")
            registros = marc.ler_mrc(pasta / ARQ_MRC)
            if not registros:
                raise RuntimeError(f"{ARQ_MRC} está vazio — refaça a conferência.")
            faltando = [i for i, r in enumerate(registros)
                        if not (r.get("035") and r["035"]["a"])]
            if faltando:
                raise RuntimeError(
                    f"{len(faltando)} registro(s) sem 035 $a: o exemplar não "
                    f"acharia a sua obra. Nada foi gravado.")
            ids = obras.inserir(con, registros, usuario=opcoes.usuario)
            resultado["obras"] = len(ids)

            progresso("exemplares", "criando exemplares e emitindo tombos")
            linhas_ex = _ler_exemplares(pasta)
            plano_exemplares = exemplares.preparar_do_csv(
                con, linhas_ex, schema=schema,
                prefixo_tombo=opcoes.prefixo_tombo or None,
                ano_tombo=opcoes.ano_tombo, biblioteca=opcoes.biblioteca,
                tipo_aquisicao=opcoes.tipo_aquisicao, usuario=opcoes.usuario)
            if plano_exemplares["nao_casados"]:
                resultado["avisos"].append(
                    f"{len(plano_exemplares['nao_casados']):,} exemplar(es) sem "
                    f"registro bibliográfico correspondente ficaram de fora.")
            exemplares.gravar(con, plano_exemplares["valores"])
            resultado["exemplares"] = len(plano_exemplares["valores"])
            resultado["prefixo_tombo"] = plano_exemplares["prefixo"]

            mapa_exemplares = [
                (linha["numacervo"], linha["id_origem"],
                 (plano_exemplares["mapa"].get(linha["id_origem"]) or ("",))[0],
                 tombo)
                for linha, tombo in zip(linhas_ex, plano_exemplares["tombos"])
            ]

        if opcoes.leitores:
            progresso("leitores", "inserindo leitores e campos personalizados")
            plano_leitores = _plano_de_leitores(tabelas_dir, opcoes)

            campos_faltando = leitores.faltando(con)
            orfas = leitores.chaves_orfas(con, plano_leitores["valores"],
                                          campos_faltando)
            if orfas:
                raise RuntimeError(
                    f"chaves de users_values sem campo em users_fields: {orfas}")
            info = leitores.inserir(
                con, plano_leitores, campos_faltando=campos_faltando,
                criar_campos=(opcoes.campos_extras == "novos"),
                email_obrigatorio=opcoes.email_obrigatorio,
                usuario=opcoes.usuario)
            resultado["leitores"] = info["leitores"]
            resultado["valores"] = info["valores"]
            resultado["campos_criados"] = info["campos_criados"]

        if opcoes.circulacao:
            progresso("circulacao", "inserindo empréstimos, multas e reservas")
            mapas = _mapas(pasta, opcoes, [], plano_leitores, con, schema,
                           provisorio=False, plano_exemplares=plano_exemplares)
            tabelas_circ = circulacao.carregar_tabelas(tabelas_dir,
                                                       opcoes.sem_reservas)
            plano_c = circulacao.montar(
                tabelas_circ["movm"], tabelas_circ["movi"], tabelas_circ["rese"],
                mapas["tombo_de"], mapas["record_de"], mapas["user_de"],
                mapas["holding_de"], id_base=mapas["id_base"],
                incluir_excluidos=opcoes.incluir_movimentacoes_excluidas,
                apenas_abertos=opcoes.apenas_abertos,
                reservas_desde=opcoes.reservas_desde)

            if plano_c["duplo_aberto"]:
                raise RuntimeError(
                    f"{len(plano_c['duplo_aberto'])} exemplar(es) com mais de um "
                    f"empréstimo em aberto. Nada foi gravado.")
            for motivo, itens in plano_c["descartes"].items():
                resultado["avisos"].append(
                    f"{len(itens):,} movimentação(ões) descartada(s) por {motivo}.")

            info = circulacao.inserir(con, plano_c, usuario=opcoes.usuario)
            resultado["emprestimos"] = info["emprestimos"]
            resultado["multas"] = info["multas"]
            resultado["reservas"] = info["reservas"]

        progresso("commit", "fechando a transação")
        con.commit()
    except Exception:
        con.rollback()
        raise

    # Daqui para baixo o banco já recebeu a carga, e nada pode mais levantar:
    # uma falha de disco ao escrever um CSV de conferência viraria "erro na
    # migração" numa tela cujo banco está gravado. Vira aviso.
    try:
        _escrever_mapas(pasta, mapa_exemplares, plano_leitores)
    except OSError as e:
        resultado["avisos"].append(
            f"A carga foi gravada, mas os mapas de conferência não puderam ser "
            f"escritos em disco ({e}).")

    # Milhares de obras novas mudam o acervo por completo, e o índice de ISBN da
    # catalogação continuaria respondendo pelo acervo de antes — todo bipe
    # viraria "obra nova" até o TTL vencer.
    _acervo.invalidar()

    resultado["terminado_em"] = datetime.now().isoformat(timespec="seconds")
    if resultado["obras"]:
        resultado["proximos_passos"].append(
            "No BibLivre: Administração → Manutenção → Reindexar base "
            "bibliográfica. Sem isso as obras existem mas não aparecem na busca.")
    if resultado["campos_criados"]:
        resultado["proximos_passos"].append(
            "Reinicie o Tomcat: UserFields e Translations são caches estáticos, "
            "e sem reiniciar os campos novos não aparecem na ficha do leitor.")
    if resultado["exemplares"]:
        resultado["proximos_passos"].append(
            "Confira em Catalogação → Exemplares e imprima uma etiqueta de "
            "teste antes de gerar o backup .b5bz.")
    return resultado


def _escrever_mapas(pasta: Path, mapa_exemplares, plano_leitores) -> None:
    """
    Os mapas de conferência, escritos só depois do commit.

    São os mesmos arquivos do `--mapa-out` dos CLIs, e são a ponte para uma
    execução parcial depois. Escrevê-los antes do commit deixaria em disco o
    mapa de uma carga que não aconteceu.
    """
    if mapa_exemplares:
        _escrever_mapa(pasta / MAPA_EXEMPLARES,
                       ["numacervo", "id_origem", "record_id", "tombo"],
                       mapa_exemplares)
    if plano_leitores is not None:
        _escrever_mapa(
            pasta / MAPA_LEITORES,
            ["numleitor", "user_id", "nome", "status"],
            [(origem["T04_NUMLEITOR"], usuario[0], usuario[1], usuario[3])
             for usuario, origem in zip(plano_leitores["usuarios"],
                                        plano_leitores["_origem"])])


def _escrever_mapa(caminho, cabecalho, linhas) -> None:
    with open(caminho, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(cabecalho)
        w.writerows(linhas)
