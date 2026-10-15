# Modelo N-M e segunda ordem — 1.8.0-rc1

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

wk N-M direccional é calculado pelas expressões (7.9), (7.11), (7.13) e (7.14), com kt=0,4, varões aderentes e Ac,eff por face. Para tracção integral, as áreas efectivas não ultrapassam h/2 por face. Para secção parcialmente traccionada, hc,eff inclui o limite (h-x)/3. k2 varia entre 0,5 e 1 conforme as extensões extremas. A tensão no aço não é truncada.

A armadura mínima N-M adopta o limite conservador kc=1 e Act=h/2 por face traccionada (7.3.2). A pesquisa de reforços ELS aumenta a malha comum de forma limitada pelas opções exequíveis; qualquer insuficiência residual permanece indicada.

O cálculo exige N assinado, momentos originais e ausência de NXY/MXY. Não avalia membrana acoplada, fendas inclinadas ou retracção impedida. São assinaladas tensões acima de 0,8fyk no aço ou 0,45fck no betão; o segundo limite evita aprovação pelo modelo linear quando os efeitos não lineares de fluência podem ser relevantes.

## Rigidez nominal

Referências: 5.8.7.2 e 5.8.7.3. Utiliza Ks=1, Kc=k1*k2/(1+phi_eff), k1=sqrt(fck/20), k2=min(n*lambda/170;0,20), gamma_CE=1,2; rho >= 0,002. NB = pi² EI/l0²; majoração 1+beta/(NB/NEd-1), beta=pi²/8 correspondente à hipótese de momento de primeira ordem constante.

NEd >= NB gera instabilidade no modelo de faixa. São considerados e_min=max(h/30;20 mm) e imperfeição simplificada e_i=l0/400. O momento majorado é verificado nos dois sentidos desfavoráveis. l0 é fornecido, não inferido dos vínculos reais. Não há análise global, acoplamento entre paredes ou verificação de flexão no plano.

## Combinações e relatórios

Listas/intervalos ELU e QP são mutuamente exclusivos. Casos não seleccionados não entram no dimensionamento. A malha comum parte dos ELU; QP verifica essa malha e pode exigir reforço por wk de flexão simples ou N-M direccional. As acções de casos diferentes não são somadas. A folha `18_NM_Stability` contém resistência N-M, parâmetros de estabilidade, majoração e tensões ELS.

## Relatório PDF

Inclui parâmetros N, l0, fluência, quadro N-M/segunda ordem e resumo QP com painéis não avaliados preservados. A largura das tabelas é limitada à área útil. Um caso sintético com dois painéis foi renderizado e inspeccionado. Esta QA não substitui ensaios com modelos reais.
