"""
Registros bibliográficos (`biblio_records`) — leitura e gravação.

    from biblio.biblivre import conexao, marc, obras

    con = conexao.conectar()
    ids = obras.inserir(con, marc.ler_mrc("obras.mrc"))
    con.commit()

POR QUE POR SQL, E NÃO PELA TELA
--------------------------------
A tela de importação funciona, mas tem dois gargalos para 14.866 registros:

1. O upload devolve TODOS os registros parseados num único JSON para o
   navegador (`Handler.importUpload`), e o Tomcat da instalação roda com heap
   de 256 MB. Um lote desse tamanho numa tacada é frágil.
2. A importação salva na base de **trabalho** (`RecordDatabase.WORK`), e mover
   para a principal exige selecionar registro por registro nos resultados
   paginados — `CatalogingHandler.moveRecords` recebe uma lista de ids montada
   a mão. Não há "mover todos".

Inserir por SQL evita os dois: grava já em `main`, sem passar pelo navegador.
É o mesmo caminho que o BibLivre usa na migração dele do Biblivre 3
(`RecordDAO.saveFromBiblivre3` insere direto em `biblio_records`).

O QUE ISTO REPRODUZ (verificado no fonte E contra 25 registros importados pela
tela, para conferência):

`BiblioRecordBO.save`:
    id      = nextval('biblio_records_id_seq')          getNextSerial(...)
    001     = id em 7 dígitos com zeros à esquerda       MarcUtils.setCF001
    005     = agora, no formato yyyyMMddHHmmss.SSS       MarcUtils.setCF005
    008     = yyMMdd + "s||||     bl|||||||||||||||||por|u"  (só se não houver)
    iso2709 = MARC serializado em UTF-8                  recordToIso2709

`RecordDAO.save`  (INSERT INTO biblio_records):
    (id, iso2709, material, database, created_by)
    material = 'book'   MaterialType.fromRecord(leader 'a'/'m ') -> BOOK, minúsculo
    database = 'main'   (aqui: já entra na base principal, pulando o WORK->MAIN)
    created_by = 1      o admin

O que o `save()` faz e este módulo NÃO faz: `indexingBo.reindex(...)`. As
tabelas `biblio_idx_*` não são preenchidas aqui — rode Administração →
Manutenção → Reindexar depois, que reconstrói o índice lendo `biblio_records`
em lotes de 30 (`IndexingBO.reindex`), seguro para o heap de 256 MB. Sem o
reindex, os registros existem mas não aparecem na busca.
"""

from collections import defaultdict
from datetime import datetime

from . import marc
from .conexao import USUARIO_PADRAO

MATERIAL = "book"       # MaterialType.BOOK.toString()
DATABASE = "main"       # entra direto na base principal

INSERT_SQL = ("INSERT INTO biblio_records (id, iso2709, material, database, created_by) "
              "VALUES (%s, %s, %s, %s, %s)")


def contar(con, database: str = DATABASE) -> int:
    with con.cursor() as cur:
        cur.execute("SELECT count(*) FROM biblio_records WHERE database = %s",
                    (database,))
        (n,) = cur.fetchone()
    return n


def contar_todos(con) -> int:
    with con.cursor() as cur:
        cur.execute("SELECT count(*) FROM biblio_records")
        (n,) = cur.fetchone()
    return n


def projetar_ids(con, quantos: int) -> list[int]:
    """
    Os ids que a sequence *entregaria*, sem consumi-la.

    `nextval()` NÃO é revertido por rollback no PostgreSQL, então o dry-run não
    pode chamá-lo: ele apenas projeta a partir do valor atual. O consumo real
    acontece em `reservar_ids`.
    """
    with con.cursor() as cur:
        cur.execute("SELECT last_value, is_called FROM biblio_records_id_seq")
        last_value, is_called = cur.fetchone()
    inicial = last_value + 1 if is_called else last_value
    return [inicial + i for i in range(quantos)]


def reservar_ids(con, quantos: int) -> list[int]:
    """Consome a sequence de fato e devolve os ids reservados."""
    if quantos <= 0:
        return []
    with con.cursor() as cur:
        cur.execute("SELECT nextval('biblio_records_id_seq') "
                    "FROM generate_series(1, %s)", (quantos,))
        return [r[0] for r in cur.fetchall()]


def inserir(con, registros, database: str = DATABASE,
            usuario: int = USUARIO_PADRAO, ids: list[int] | None = None) -> list[int]:
    """
    Insere registros MARC em `biblio_records`, carimbando 001/005/008.

    Não commita: quem chama decide, porque obras e exemplares fecham na mesma
    transação. Devolve os ids atribuídos, na ordem dos registros.
    """
    registros = list(registros)
    if not registros:
        return []

    ids = ids if ids is not None else reservar_ids(con, len(registros))
    if len(ids) != len(registros):
        raise ValueError(f"{len(ids)} id(s) para {len(registros)} registro(s)")

    agora = datetime.now()
    valores = [
        (rec_id, marc.carimbar(rec, rec_id, agora), MATERIAL, database, usuario)
        for rec_id, rec in zip(ids, registros)
    ]

    from psycopg2.extras import execute_batch

    with con.cursor() as cur:
        execute_batch(cur, INSERT_SQL, valores, page_size=500)
    return ids


def mapa_por_035(con) -> tuple[dict, dict, list]:
    """
    Mapa `(BF)N -> (record_id, database, subcampos do 090)`.

    É assim que o exemplar acha a sua obra: o BibLivre sobrescreve 001/005/008
    ao salvar, então o `NUMACERVO` de origem viaja no 035 $a. Devolve também os
    035 repetidos e os registros sem 035, que o chamador reporta.
    """
    with con.cursor() as cur:
        cur.execute("SELECT id, database, iso2709 FROM biblio_records")
        linhas = cur.fetchall()

    mapa: dict = {}
    duplicados: dict = defaultdict(list)
    sem_035: list = []

    for rec_id, database, iso in linhas:
        registro = marc.do_iso2709(iso)
        if registro is None:
            sem_035.append(rec_id)
            continue

        # pymarc 5.x: registro["035"] lança KeyError se o campo não existir;
        # .get() devolve None.
        campo035 = registro.get("035")
        origem = campo035.get("a") if campo035 is not None else None
        if not origem:
            sem_035.append(rec_id)
            continue

        if origem in mapa:
            duplicados[origem].append(rec_id)
        else:
            mapa[origem] = (rec_id, database, _loc090(registro))

    return mapa, dict(duplicados), sem_035


def localizacoes(con, record_ids: list[int]) -> dict[int, dict]:
    """090 $a/$b/$c de cada registro — o exemplar herda a localização da obra."""
    if not record_ids:
        return {}
    with con.cursor() as cur:
        cur.execute("SELECT id, iso2709 FROM biblio_records WHERE id = ANY(%s)",
                    (list(record_ids),))
        linhas = cur.fetchall()
    return {rec_id: _loc090(marc.do_iso2709(iso)) for rec_id, iso in linhas}


def _loc090(registro) -> dict:
    if registro is None:
        return {}
    campo = registro.get("090")
    if campo is None:
        return {}
    return {c: (campo.get(c) or "").strip() for c in "abc"}
