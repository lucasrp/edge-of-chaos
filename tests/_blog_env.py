"""Guarda das variáveis de ambiente do blog — restaura o que o teste sujar.

Doze módulos setavam `EDGE_BLOG_STATIC`, onze `EDGE_BLOG_ENTRIES` e doze `EDGE_BLOG_LOG`
apontando para o próprio `TemporaryDirectory`. Um limpava. Como o diretório é apagado no
`tearDown` mas a VARIÁVEL fica, o módulo seguinte que não declarasse o próprio caminho lia um
diretório que não existe mais — e o resultado da suíte passava a depender da ORDEM dos módulos.

O modo de falha não é erro: é silêncio. O servidor degrada (sem `style.css`, sem entradas), o
teste vê uma página vazia e afirma o que der. Num `assertIn` isso vira um vermelho legítimo —
foi assim que o #623 apareceu. Num `assertNotIn` ou num `assertEqual(..., [])` vira VERDE
FALSO, e ninguém olha um verde.

Uso, na primeira linha do `setUp` que mexe no ambiente:

    from _blog_env import guard_blog_env
    ...
    guard_blog_env(self)

`addCleanup` roda depois do `tearDown` e sobrevive a exceção no meio do teste, que é
justamente quando o vazamento seria pior.
"""
import os

BLOG_ENV_VARS = ("EDGE_BLOG_STATIC", "EDGE_BLOG_ENTRIES", "EDGE_BLOG_LOG")


def guard_blog_env(testcase, *extra):
    """Tira uma foto das variáveis do blog e agenda a restauração ao fim do teste."""
    for name in BLOG_ENV_VARS + tuple(extra):
        before = os.environ.get(name)
        testcase.addCleanup(_restore, name, before)


def _restore(name, before):
    if before is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = before
