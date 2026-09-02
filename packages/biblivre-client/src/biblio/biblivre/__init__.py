"""
Cliente do BibLivre 5 — tudo que fala com o PostgreSQL dele.

Nasceu de uma série de scripts soltos que existiam para migrar um acervo do
Biblioteca Fácil. A lógica era boa e está validada em campo (14.866 obras,
16.251 exemplares, 2.743 leitores e 19.592 empréstimos carregados numa
instância real), mas só existia dentro de `argparse` — não dava para reusar.
Aqui ela é biblioteca: os CLIs em `scripts/` viraram casca fina por cima disto,
e a API HTTP chama os mesmos módulos.

    conexao      credenciais, `conectar()`, `search_path`, diagnóstico
    marc         montar/ler ISO 2709 (sem tocar no banco)
    obras        `biblio_records` — inserir, mapear pelo 035 $a
    exemplares   `biblio_holdings` — MARC do exemplar, tombos, inserir
    acervo       índice ISBN -> obra: "este livro já está catalogado?"
    leitores     `users` + `users_values` + `users_fields`
    circulacao   `lendings` + `lending_fines` + `reservations`

REGRA QUE ATRAVESSA O PACOTE: **nada aqui commita.** Toda função de gravação
recebe a conexão e deixa o commit para quem chamou, porque obras e exemplares
precisam fechar na mesma transação — não existe "gravou metade".

O outro invariante é o reindex: inserir em `biblio_records` não preenche
`biblio_idx_*`. Depois de criar obra nova é preciso passar em Administração →
Manutenção → Reindexar, senão o registro existe e não aparece na busca. Só
exemplar novo não precisa.
"""

from . import acervo, circulacao, conexao, exemplares, leitores, marc, obras

__all__ = ["acervo", "circulacao", "conexao", "exemplares", "leitores",
           "marc", "obras"]
