# WallsEC2 — evidência de validação e condições de aceitação

**Estado: v2.0.0-rc1 — pacote para testes de aceitação, não validação regulamentar integral.**

## Revisão de distribuição

338 testes sintéticos aprovados em Linux/Tk, incluindo três novos testes da interface e da auditoria de entrada. Arranque e ícone confirmados. Não se modificou o motor de dimensionamento nesta revisão; não se repetiram os 66 painéis históricos.

## Auditoria precedente (rc1-audit)

335 testes sintéticos aprovados em Linux. Um novo conjunto de oito painéis e 26400 registos (17424 ELU, 528 QP) foi recalculado com os parâmetros originais. Resultados ELU reproduzidos; 528/528 QP sem excedência do limite inferior de tração no modelo elástico condicional. 4224 CAR e 528 QP com limites de tensão satisfeitos condicionalmente. Quatro painéis com limites seccionais satisfeitos sob hipóteses e quatro condicionados. 108 linhas excedem o limite de triagem do sandwich, 514 linhas sem demonstração da secção 6.109 após excluir as alternativas elásticas e 532 linhas que exigem confirmação complementar LL(115)(c). Nenhuma pendência de segunda ordem por faixa. Estes resultados não provam integridade física. Não se repetiu nesta revisão a totalidade dos 66 painéis anteriores.


## Regressão histórica de cálculo (versão rc1-candidate)

Oito conjuntos privados, 66 painéis e 220750 registos (145695 ELU e 4415 QP). Zero erros de execução. Os ficheiros privados, as geometrias e as identificações de painéis não integram a distribuição. Foram utilizadas as hipóteses dos ensaios anteriores, com kX=kY=1, RH=70%, t0=28 dias e duas faces expostas quando a estabilidade automática foi utilizada; são parâmetros de ensaio, não confirmação de apoios reais.

| Indicador | Valor |
|---|---:|
| Utilização local máxima | 0.939813 |
| Utilização sandwich máxima | 1.459594 |
| Linhas sandwich acima da unidade (inclui limites de triagem) | 83 |
| Linhas sem resultado sandwich | 0 |
| Condições 6.109 não demonstradas no ramo fendilhado | 97091 |
| Corte adicional LL.115 condicionado no ramo fendilhado | 104069 |
| Linhas com alternativa LL(103)/(107) condicional | 99162 |
| Linhas com incrementos locais pendentes | 17275 |
| QP com wk convencional calculado | 0 |
| QP com abertura por cargas condicional | 4221 |
| Painéis com limites ELS 7.2 satisfeitos nos modelos aplicáveis | 37 |
| Painéis condicionados | 66 |

As contagens de condições não são disjuntas. A ultrapassagem de um limite de triagem não é uma não conformidade regulamentar comprovada. A existência de equilíbrio e de utilização inferior a 1 não substitui a demonstração das condições 6.109 nem do corte adicional. A regressão atual inclui a envolvente dos incrementos locais; não comparar diretamente a antiga utilização de primeira ordem sem essa envolvente.

## Ensaios e verificações históricas

- 333 testes sintéticos da distribuição limpa aprovados em Linux/Tk. Incluem solução analítica de campos alinhados, verificação independente do equilíbrio, limites F.1, reserva de corte verificada em 361 direções, importação de limite externo com identidade do cálculo e cobertura, 7.2 por combinação e modelo uniaxial, importação pela GUI sem promoção de estado global.
- Arranque com ícone e ensaio sintético aprovado. Exportação real PDF e XLSX de um conjunto de 7 painéis (7850 registos, 5181 ELU e 157 QP); ficheiro XLSX com 30 folhas, integridade ZIP confirmada e leitura da folha 31_ELS_Tensoes_72. 1256 CAR e 157 QP satisfeitos no cenário elástico condicional; 1256 FREQ sem limite autónomo 7.2. Utilização máxima sandwich 0,280911, armaduras Ø8//200 preservadas, reserva de corte de 69,371 a 76,827 kN/m. O caso não prova integridade física nem estanquidade.

## Limites de aceitação

| Referência | Avaliação | Condição necessária |
|---|---|---|
| 6.109 e Anexo F | Campos equilibrados, solução analítica alinhada, ramos 6.110/6.111/6.112, limite inferior de triagem separado | Demonstrar campo admissível e referência elástica efetiva; alternativa íntegra apenas se história física demonstrada |
| LL(115)(c) | Reserva conservadora de corte e comparação com limite superior externo | Determinar campo espacial adicional e confirmar cobertura, continuidade, armaduras e validade espacial da reserva; dados não fornecidos |
| 5.8 | Segunda ordem por faixa X/Y; incrementos na envolvente sandwich | Travamentos, comprimentos e fluência; estabilidade global externa |
| 7.2 | Limites CAR e limiar QP, modelos íntegro e uniaxial | Hipóteses de serviço, coacção e histórico; condições não demonstradas no domínio acoplado |
| 7.3.4 / EN 1992-3 | Fendilhação convencional e avaliação condicional por cargas | Fendilhação acoplada fora do âmbito; estanquidade e deformações impostas requerem avaliação específica |
| Distribuição | Pacote fonte, ícone e configuração PyInstaller | Compilar e ensaiar nativamente em Windows antes de publicar |

A RC1 não está regulamentarmente encerrada para todos os casos. Uma ficha de limite externo só permite verificar a reserva quando a avaliação espacial é fundamentada; não é uma validação automática da análise externa. Nenhum dado ausente é presumido igual a zero.
