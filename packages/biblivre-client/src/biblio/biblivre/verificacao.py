"""
Conferência pós-carga: as perguntas que só o banco inteiro responde.

    from biblio.biblivre import conexao, verificacao

    relatorio = verificacao.conferir(conexao.conectar())

O roteiro de importação termina mandando "conferir em Catalogação → Exemplares
e imprimir uma etiqueta de teste". A etiqueta é conferência de papel — margem,
impressora, se o leitor da biblioteca lê o que saiu — e nenhuma automação
responde isso. Já a conferência de dados é consulta, e automatizada cobre as
16.251 linhas em vez de uma amostra de olho.

A CHECAGEM QUE JUSTIFICA O MÓDULO
---------------------------------
`biblio_records` sem linha em `biblio_idx_fields` é a única resposta objetiva
para "o reindex funcionou?". Hoje ninguém sabe sem abrir a busca do BibLivre e
procurar um título de cor.

E a armadilha: a migração grava **id explícito** (preserva a numeração de
origem). Se as sequences ficaram atrás do `max(id)`, o primeiro empréstimo
feito pelo app estoura chave duplicada — no balcão, com fila.

Só leitura: nenhum INSERT, nenhum UPDATE, nenhum commit.

ESQUELETO DO INTEGRADOR
-----------------------
Contrato em docs/PLANO_AGENTES.html §4.1; implementação é do pacote **A2**,
que também escreve o CLI `scripts/conferir.py`.
"""

_FALTA = "biblio.biblivre.verificacao: pendente (pacote A2 do plano de agentes)"


def conferir(con) -> dict:
    """
    -> {"checagens": [{"chave","rotulo","ok","valor","esperado","detalhe"}],
        "resumo": {"ok": n, "falhas": n}}

    Checagem que não pôde rodar (tabela ausente, permissão) volta com
    `ok=None` e o motivo — nunca derruba as outras.
    """
    raise NotImplementedError(_FALTA)
