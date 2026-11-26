# v2.0.0-rc1

- Interface e documentação de utilização alinhadas com os oito esforços concomitantes.
- Dashboard e vistas de engenharia simplificados; auditoria explícita de todos os componentes importados.
- Identificadores internos e dados completos preservados nas exportações.
- Fluxo Windows x64 de testes, compilação, smoke test e publicação como pré-release.
- Sem alteração ao motor resistente da revisão rc1-audit. Mantêm-se os limites regulamentares documentados.

# Changelog

## v2.0.0-rc1-audit
- Estado seccional separado das hipóteses gerais de utilização; não penaliza automaticamente a estabilidade externa, a amarração geral ou a via fendilhada quando a alternativa elástica é aplicável. As verificações resistentes não demonstradas permanecem condicionadas.
- Limite superior de tensão principal refinado por discretização certificada do campo elástico ao longo da espessura (inclui Q); não altera fctk nem atribui wk regulamentar.
- Relatório compacto; omite secções experimentais e informação redundante. Mantém LL(115)(c), 6.109 e as hipóteses necessárias.
- 335 testes sintéticos aprovados; novo recálculo de oito painéis e 26400 registos com as hipóteses do cálculo de origem. 528/528 linhas QP com ausência condicional de fendas por cargas. Os resultados ELU mantêm-se; quatro painéis condicionados.


## v2.0.0-rc1-candidate (testes de aceitação; validação regulamentar não encerrada)
- Solução analítica adicional de campos alinhados 6.111 com equilíbrio de excentricidades e limites de F.1.
- Reserva de corte adicional LL.115 independente da direção; ficha de limite externo com cobertura e identificação do cálculo e relatório.
- Critérios de tensões ELS CAR/QP, identificação do limiar de fluência não linear e avaliação estritamente uniaxial fendilhada.
- Estados condicionados consistentes nos resumos e exportações; referências de cálculo e parâmetros com notação de engenharia.
- Sem promoção automática das condições por demonstrar; sem análise autónoma de estabilidade de casca.

## v2.0.0-dev-validacao.4 (teste)
- Nomenclatura: resistência dos campos comprimidos; corte adicional por transferência intercamadas.
- Via alternativa LL(103)/(107) com limite superior em toda a espessura e em todos os estados discretos da envolvente. Não presume histórico sem fendas.
- Máxima norma da correção de forças de membrana na envolvente, distinta de corte adicional.
- 326 testes sintéticos aprovados; recálculo do reservatório, 5181/5181 linhas ELU elegíveis para a alternativa condicional; resultados anteriores do sandwich preservados.
- LL(115)(c) e 6.109 mantidos no ramo fendilhado; sem aprovação integral.

## v2.0.0-dev-validacao.3 (teste)
- Retirada a segunda ordem acoplada; mantidas as faixas X/Y.

## v2.0.0-dev-validacao.2 (teste)
- Integração da envolvente discreta dos incrementos de imperfeição/segunda ordem de faixa no sandwich e na otimização; mantida a condição de compressão oblíqua.
- Estado ELU calculado, ELS por cargas, segunda ordem local e revisão global apresentados separadamente.
- Notação de engenharia nos cabeçalhos, símbolos gregos e subscritos no PDF; redução de tabelas e mensagens redundantes.

## v2.0.0-dev-validacao.1 (teste)

- Avaliação elástica ELS por cargas, com valor de abertura condicional separado de wk convencional.
- Estados locais ELU e pendências globais apresentados separadamente; cobertura de combinações com intervalos em falta.
- Diálogos estruturados de fluência e comprimento efectivo, modo manual/automático visível.
- Relatório mais compacto, sem repetição de diagnósticos de métodos excluídos.
- 318 testes sintéticos aprovados em Linux e recálculo de 7 painéis/7850 linhas do caso privado, sem dados de projeto distribuídos.

## v2.0.0-dev-validacao (não publicada)

- Modelo sandwich de primeira ordem com Anexo F, forças de face, correção de excentricidade, espessuras simétricas/assimétricas e transferência da treliça.
- Procura explícita de campos com cedência de uma família de aço (F.8–F.10 e 6.112); cobertura da compressão principal oblíqua na segunda ordem.
- Critérios 6.110/6.111/6.112 com limites F.1, redistribuição F.8-F.10, indicação de condições não demonstradas, transferência LL.115 por verificar externamente.
- Integração na otimização base + reforços e apresentação única de resultados de casca na GUI, PDF, XLSX e lote.
- Exclusão da fendilhação inclinada e MCFT do âmbito de dimensionamento; manter wk convencional e avisos de cobertura.
- Preservação de testes históricos; dados privados excluídos. Distribuição para teste, não versão aprovada.
