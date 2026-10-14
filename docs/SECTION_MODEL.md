# Modelo N-M e segunda ordem — 1.7.0-rc1

## Convenções e constituição

Faixa de largura 1000 mm; espessura h; duas camadas de aço nas faces. Internamente N positivo significa compressão. M positivo comprime a face - e tracciona a face +. O utilizador confirma a convenção N da tabela de origem. NXX/MXX e NYY/MYY são tratados como verificações direccionais independentes; NXY não é dimensionado.

A coordenada das camadas reserva o recobrimento, uma camada ortogonal exterior igual à maior bitola seleccionável e metade do maior diâmetro adoptado entre as faces. É uma hipótese conservadora; não é uma definição exacta da posição de cada família numa malha heterogénea.

## Resistência

Referências: NP EN 1992-1-1:2010, 3.1.7 e 6.1. Betão parábola-rectângulo, sem tracção; parâmetros de extensão/expoente variáveis com fck. Aço elástico-perfeitamente plástico limitado a fyd, com extensão última de cálculo seleccionável.

Extensões lineares no plano da secção. Integração por fibras e desconto da área de betão ocupada pelas duas camadas de aço. Domínios de extensão construídos a partir dos limites eps_ud, eps_cu e do ponto C em compressão. Nos ramos com limite de tracção, esse limite é aplicado à face extrema do betão, conservador face à camada de aço interior.

A intersecção da curva de compatibilidade com NEd fornece os limites de momento positivo e negativo. N fora do domínio resistente gera «Não conforme». A discretização predefinida é 160 fibras e 160 pontos por ramo; os testes com 320 fibras/pontos verificam a convergência em casos representativos. A convergência não é automaticamente garantida para todas as geometrias/armaduras possíveis.

A escolha de aço tenta acrescentar armadura às duas faces para N-M; se as opções de diâmetro/espaçamento se esgotarem, a verificação conserva a insuficiência da solução disponível. Esta pesquisa não garante um óptimo económico global.

## ELS

Equilíbrio N-M elástico com betão traccionado desprezado; Ecm efectivo = Ecm/(1+phi_eff). A secção é resolvida por conjuntos activos de fibras comprimidas e o resíduo de equilíbrio é verificado. Tensões no aço não são truncadas artificialmente. Para esforços Wood-Armer separados, são necessários os momentos originais assinados para esta resolução; as envolventes positivas/negativas não são subtraídas para inventar um momento ELS.

wk N-M ainda não é calculado. O resultado wk é omitido para QP com esforços de membrana não nulos e o estado assinala verificação em falta.

## Rigidez nominal

Referências: 5.8.7.2 e 5.8.7.3. Utiliza Ks=1, Kc=k1*k2/(1+phi_eff), k1=sqrt(fck/20), k2=min(n*lambda/170;0,20), gamma_CE=1,2; rho >= 0,002. NB = pi² EI/l0²; majoração 1+beta/(NB/NEd-1), beta=pi²/8 correspondente à hipótese de momento de primeira ordem constante.

NEd >= NB gera instabilidade no modelo de faixa. São considerados e_min=max(h/30;20 mm) e imperfeição simplificada e_i=l0/400. O momento majorado é verificado nos dois sentidos desfavoráveis. l0 é fornecido, não inferido dos vínculos reais. Não há análise global, acoplamento entre paredes ou verificação de flexão no plano.

## Combinações e relatórios

Listas/intervalos ELU e QP são mutuamente exclusivos. Casos não seleccionados não entram no dimensionamento. A malha comum parte dos ELU; QP verifica essa malha e pode exigir reforço por wk de flexão simples. As acções de casos diferentes não são somadas. A folha `18_NM_Stability` contém resistência N-M, parâmetros de estabilidade, majoração e tensões ELS.
