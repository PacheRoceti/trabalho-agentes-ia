"""A versão do sistema (Parte 3, §4.2): vai à raiz de cada trace (`triagem.versao` e o
`service.version` do recurso) e é o padrão do `--versao` da suíte (evals/rodar.py). Sem ela, nenhum
número se compara entre versões.

Muda quando muda o comportamento do sistema (código de decisão, prompt, modelo, busca), e cada
mudança vai ao docs/mudancas.md com o commit. O commit continua indo ao log e ao trace: a versão diz
o que se pretendia medir; o commit, o que rodou.
"""
VERSAO = "1.1.0"
