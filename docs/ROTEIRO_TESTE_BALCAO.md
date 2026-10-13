# Roteiro do primeiro teste do balcão contra o BibLivre real

É a pauta do [ROADMAP](ROADMAP.md) ("O primeiro teste contra o BibLivre
real"), escrita para ser seguida na frente do PC da biblioteca. A ordem importa:
cada etapa desarma o risco da seguinte. Se uma etapa falhar, **pare ali**. Anote
o que apareceu na tela e o fim de `data/logs/servidor.log`, e não siga para a
próxima.

Duas pessoas ajudam: uma no PC e outra com o celular e os livros. Conte com
1h a 1h30.

---

## 0. Antes de começar

- [ ] **Backup do BibLivre** pela tela dele: Administração → Backup → Full.
      Guarde o `.b5bz` fora do PC (pendrive). É o que desfaz qualquer coisa
      daqui para baixo.
- [ ] Separe para o teste:
  - um **leitor de teste** (de preferência um funcionário, que já sabe do
    teste). Anote o número dele: ____
  - **três livros** migrados do Biblioteca Fácil, com o número de registro
    (NUMACERVO) escrito neles. Um deles precisa ter ISBN na capa. Anote os
    números: ____ / ____ / ____
  - se houver, uma **etiqueta impressa pelo BibLivre** (de exemplar) e uma
    **carteirinha** impressa por ele.
- [ ] Login e senha de um operador do BibLivre que **não** seja o `admin`.
- [ ] O `.env` na raiz do projeto tem a senha do Postgres (`PGPASSWORD`).

## 1. Instalação e abertura

```
git pull
python scripts/inicializacao.py instalar --rebuildar
```

- [ ] O Windows pergunta se confia no certificado: clique em **Sim**.
- [ ] O `status` no fim diz "no ar agora: sim".
- [ ] Na Área de Trabalho apareceu o ícone **BiblioFácil** (livro aberto).
      Dê dois cliques: abre uma janela própria, **sem barra de endereço e sem
      aviso de conexão**.
- [ ] O BiblioFácil aparece no menu Iniciar (dá para fixar na barra de
      tarefas).
- [ ] Reinicie o PC e entre no Windows. Sem abrir nada, em menos de um minuto
      o ícone abre o sistema. É a prova de que ele sobe sozinho.

Se a janela mostrar "conexão não é particular": o certificado não ficou
confiável. Anote e siga em frente pelo **Avançado → Continuar**, porque não
bloqueia o teste.

## 2. Conferência da base (só leitura)

```
python scripts/conferir.py
```

- [ ] Nenhuma linha **FALHA**. Olhe com atenção as **sequences**: uma sequence
      atrasada faz o primeiro empréstimo estourar com chave duplicada.
- [ ] Se falhar: **pare aqui** e guarde a saída inteira.

## 3. Entrar como operador

Abra **Circulação** e entre com o login do operador.

- [ ] O login entra. Um login errado é recusado com mensagem clara.
- [ ] O nome do operador aparece na tela.

(A confirmação de que ele foi gravado como autor do empréstimo vem na etapa 6.)

## 4. Achar o livro (sem emprestar nada)

Na barra principal do PC, um por vez:

| Digite | Esperado | Deu certo? |
|---|---|---|
| o número de registro do livro 1 (ex.: `842`) | abre o exemplar certo, título certo | |
| o mesmo número **com zeros** (ex.: `000842`) | anote o que acontece | |
| o ISBN do livro com ISBN | mostra a obra e **todos** os exemplares, com o estado de cada um | |
| parte do título, sem acento (ex.: `memorias postumas`) | lista a obra; escolher abre o exemplar | |
| sobrenome do autor | também acha | |
| o número do leitor de teste | abre a ficha do leitor | |

- [ ] Se o número de um livro é **igual** ao número de algum leitor, a tela
      oferece os dois (livro e ficha do leitor). Anote se foi o caso.
- [ ] **Etiqueta do BibLivre:** bipe a etiqueta impressa pelo BibLivre com o
      leitor USB. **Isto é o mais importante a descobrir.** Pelo código fonte,
      a etiqueta traz o id interno com 10 dígitos (`0000000123`), não o
      número de registro, e pode cair num **leitor** em vez do livro. Anote o
      que apareceu: __________
- [ ] **Carteirinha:** bipe a carteirinha impressa. Abre o leitor certo?

## 5. Leitor USB no balcão

- [ ] Bipe um livro: os dígitos entram e o Enter dispara a busca, sem clicar
      no campo antes.
- [ ] Clique em algum botão e bipe de novo **sem clicar no campo**. Ainda
      funciona?

## 6. Empréstimo de teste

Com o leitor de teste, empreste o **livro 1**.

- [ ] O empréstimo é aceito. Anote a data de devolução que o app mostrou:
      ____
- [ ] Abra o **BibLivre** e procure o mesmo leitor em Circulação. O
      empréstimo está lá, com a **mesma data de devolução** e o operador
      certo.
- [ ] Se a biblioteca abre aos sábados, confira se o prazo contou o sábado.
      Se não contou, a configuração de dias úteis do BibLivre diz que não abre
      no sábado. Isso se ajusta lá, não no código.
- [ ] Tente emprestar o **mesmo livro** de novo: o app recusa, dizendo que
      já está emprestado.

## 7. Renovação

- [ ] Renove o empréstimo do livro 1. A nova data aparece no app **e** no
      BibLivre.

## 8. Devolução

- [ ] Devolva o livro 1. Ele some da ficha do leitor no app e no BibLivre.
- [ ] Multa: com empréstimo do dia não deve haver multa. Se a biblioteca
      cobra multa, confira se o valor está configurado no BibLivre (tipo de
      leitor → valor da multa). Sem isso, nenhuma multa é gravada.
- [ ] Se o livro tinha reserva, aparece o aviso de separar para o leitor
      que reservou.

## 9. Pelo celular

No celular, ligado ao Wi-Fi da biblioteca, abra o endereço que o `status`
mostra (`https://<IP-DO-PC>:8000/circulacao`) e aceite o certificado.

- [ ] Empreste o **livro 2** bipando a carteirinha (ou digitando o número do
      leitor) e depois o livro.
- [ ] Busque o **livro 3** pelo título.
- [ ] Devolva o livro 2 pelo celular. A devolução aparece no BibLivre.

## 10. Manutenção (ainda sem tela)

Abra `https://localhost:8000/docs`. Em cada rota, use **Try it out → Execute**.
Essas rotas exigem um operador logado:

- [ ] `POST /api/sessao` com `{"usuario": "...", "senha": "..."}`. Copie o
      `token` da resposta e cole no campo **x-sessao** de cada rota abaixo.
- [ ] `POST /api/manutencao/biblivre` com `url` (normalmente
      `http://localhost:8080/Biblivre5/`), `usuario` e `senha` do
      administrador do BibLivre. A resposta deve vir com `conectado: true`.
- [ ] `POST /api/manutencao/reindexar` e depois, algumas vezes,
      `GET /api/manutencao/reindexar` até terminar. A busca do **BibLivre**
      continua achando os livros depois.
- [ ] `POST /api/manutencao/backup` e depois `GET /api/manutencao/backup`:
      o `.b5bz` é gerado.

## 11. Fechar

- [ ] Nenhum empréstimo de teste ficou aberto (confira a ficha do leitor de
      teste no BibLivre).
- [ ] `python scripts/conferir.py` de novo, sem FALHA.
- [ ] Anote abaixo o que falhou ou estranhou e marque os itens no
      [ROADMAP](ROADMAP.md).

### Anotações

| Etapa | O que aconteceu | Print / trecho do log |
|---|---|---|
| | | |
