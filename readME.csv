Abaixo está a documentação completa do sistema UltraBot 5.2 Backtester, incluindo a estrutura dos arquivos, as funcionalidades implementadas com base em nossa conversa, e a engenharia por trás da criação. Esta documentação reflete o estado atual do código, as melhorias realizadas, e as possibilidades de expansão discutidas.

Documentação do UltraBot 5.2 Backtester
Visão Geral
O UltraBot 5.2 Backtester é um bot de trading automatizado projetado para operar no mercado de futuros da Binance, com suporte para os pares XRPUSDT, DOGEUSDT, e TRXUSDT. Ele foi desenvolvido para coletar dados em tempo real, gerar sinais de trading baseados em indicadores como order book, delta volume, open interest, e funding rate, e registrar os resultados em logs detalhados. O sistema suporta dois modos de operação: produção (real) e dry run (testnet), permitindo testes seguros antes de operar com capital real.

O bot foi construído em Python, utilizando a biblioteca python-binance para interação com a API da Binance Futures, e foi projetado com uma arquitetura modular para facilitar manutenção e expansão.

Estrutura de Arquivos
A estrutura do projeto é composta por três arquivos principais, todos localizados no diretório /Users/leovieira/Downloads/UltraBot_5.2 backtester/:

config.py:
Descrição: Arquivo de configuração que armazena chaves da API, pares negociados, timeframes, e modo de execução.
Conteúdo:
python

Recolher

Encapsular

Copiar
# config.py
REAL_API_KEY = "VGQ0dhdCcHjDhEjj0Xuue3ZtyIZHiG9NK8chA4ew0HMQMywydjrVrLTWeN8nnZ9e"
REAL_API_SECRET = "jHrPFutd2fQH2AECeABbG6mDvbJqhEYBt1kuYmiWfcBjJV22Fwtykqx8mDFle3dO"
DRY_RUN_API_KEY = "g9mSN8ic44DqKKcyCSqKatm1H3H8RISsBbz64TixKU1vgqMLwAIkoGJWQ0F7zPs3"
DRY_RUN_API_SECRET = "g4UKf1z0vGLVCqTUuWg1qA5SLvvvIfTtZYgxlCaeVcDZmUgEUfK8z6agx8JUX1CY"
SYMBOLS = ["XRPUSDT", "DOGEUSDT", "TRXUSDT"]
TIMEFRAMES = ["15m", "1h", "2h", "4h"]
DRY_RUN = True
binance_utils.py:
Descrição: Módulo utilitário que encapsula as interações com a API da Binance Futures.
Funcionalidades:
get_order_book: Obtém o livro de ordens.
calculate_delta_volume: Calcula o delta de volume com base em trades recentes.
get_open_interest: Recupera o open interest.
get_funding_rate: Recupera a taxa de funding.
main.py:
Descrição: Arquivo principal que coordena a lógica do bot, gera sinais e registra os resultados.
Funcionalidades:
UltraBot: Classe principal do bot.
analyze_timeframes: Analisa alinhamento de timeframes (atualmente simulado).
get_current_price: Obtém o preço atual.
generate_signal: Gera sinais de trading.
log_signal: Registra os sinais no log.
Funcionalidades Implementadas
Com base em nossa conversa, as seguintes funcionalidades foram desenvolvidas e integradas ao UltraBot 5.2 Backtester:

Modos de Operação:
Produção (Real): Usa as chaves REAL_API_KEY e REAL_API_SECRET para operar no ambiente real da Binance Futures (https://fapi.binance.com).
Dry Run (Testnet): Usa as chaves DRY_RUN_API_KEY e DRY_RUN_API_SECRET para operar no ambiente de teste (https://testnet.binancefuture.com). Configurado como padrão (DRY_RUN = True).
Pares Negociados:
Suporte para três pares específicos: XRPUSDT, DOGEUSDT, e TRXUSDT, definidos em SYMBOLS.
Coleta de Dados em Tempo Real:
[ICEBERG] Order Book: Recupera o livro de ordens para análise de liquidez.
[DELTA] Delta Volume: Calcula o volume líquido (compras menos vendas) com base em trades recentes.
[SENTIMENTO] Open Interest: Monitora o interesse aberto no mercado.
[SENTIMENTO] Funding Rate: Obtém a taxa de funding para avaliar o sentimento do mercado.
Geração de Sinais:
Combina dados de order book, delta volume, open interest, funding rate, e preço atual para gerar sinais.
Inclui uma lógica de pontuação (score) e verificação de alinhamento de timeframes (simulada atualmente).
Sinais são registrados com detalhes como timestamp, par, timeframe, direção, preço atual, score, e ação (aceito/recusado).
Logging Detalhado:
Usa o módulo logging para registrar eventos em tempo real, incluindo sucesso/erro nas chamadas à API e sinais gerados.
Formato estruturado com caixas de texto para sinais (ex.: ┌─ ... ─┐).
Execução Contínua:
O bot opera em um loop infinito, analisando cada par a cada 60 segundos.
Engenharia por Trás da Criação
A construção do UltraBot 5.2 Backtester seguiu princípios de engenharia de software para garantir robustez, modularidade, e escalabilidade. Aqui está o processo e as decisões tomadas:

1. Arquitetura Modular
Separação de Responsabilidades:
config.py: Armazena configurações, isolando credenciais e parâmetros do código principal.
binance_utils.py: Encapsula a lógica de interação com a API, permitindo reutilização e fácil manutenção.
main.py: Coordena a lógica de alto nível e geração de sinais.
Benefícios:
Facilita a adição de novos indicadores ou pares sem alterar a lógica central.
Torna o código mais legível e testável.
2. Tratamento de Erros
Exceções Específicas: Captura erros como BinanceAPIException, AttributeError, JSONDecodeError, e RequestException para evitar falhas inesperadas.
Logs Informativos: Cada erro é registrado com detalhes para facilitar o debug (ex.: [ICEBERG] Erro na API...).
Resiliência: O bot continua funcionando mesmo se uma chamada à API falhar para um par específico.
3. Integração com a API da Binance
Endpoints Corretos: Após corrigir o uso inicial de uma URL de página web (binancefuture.com), foram adotados os endpoints oficiais da API Futures (fapi.binance.com e testnet.binancefuture.com).
Testnet como Padrão: Configurado para operar em modo seguro (DRY_RUN = True) até que a lógica esteja validada.
Rate Limits: Inclui pausas (time.sleep(60)) para evitar ultrapassar os limites de taxa da API.
4. Geração de Sinais (Simulada)
Lógica Inicial: A função analyze_timeframes simula o alinhamento de timeframes como um placeholder, retornando 1 apenas para "15m".
Pontuação: Sinais recebem um score de 10 ou 40 com base no alinhamento (menos de 2 ou 2+ timeframes), com rejeição se < 50.
Expansibilidade: Projetado para integrar análise técnica real (ex.: RSI, MACD) com bibliotecas como ta e pandas.
5. Resolução de Problemas
ImportError: Corrigido ao garantir que config.py estivesse no mesmo diretório e sem erros de sintaxe.
Caminho do Diretório: Identificado que o diretório correto é UltraBot_5.2 backtester (com espaço), ajustando os comandos conforme necessário.
Permissões: Sugerida a verificação de permissões, mas não foi necessária após confirmar a estrutura.
Possibilidades de Expansão
Com base em nossa conversa, aqui estão as funcionalidades discutidas que podem ser implementadas:

Análise Técnica Avançada:
Integrar indicadores como RSI, MACD, ou médias móveis usando pandas e ta.
Exemplo:
python

Recolher

Encapsular

Copiar
from ta.trend import SMAIndicator
sma_fast = SMAIndicator(df['close'], window=10).sma_indicator()
sma_slow = SMAIndicator(df['close'], window=50).sma_indicator()
Execução de Ordens:
Adicionar chamadas à API para criar ordens de teste no testnet:
python

Recolher

Encapsular

Copiar
order = self.binance.client.create_test_order(symbol=symbol, side="BUY", type="MARKET", quantity=10)
Critérios de Trading:
Definir direção (LONG/SHORT) com base em delta volume, funding rate, e alinhamento de timeframes.
Exemplo:
python

Recolher

Encapsular

Copiar
if delta_volume > 0 and aligned_timeframes >= 2:
    signal["direction"] = "LONG"
Backtesting:
Adicionar suporte para dados históricos usando get_historical_klines para simular estratégias antes de operar em tempo real.
Parada Controlada:
Substituir o loop infinito por um número fixo de iterações ou um comando de parada manual.
Pré-requisitos
Python: Versão 3.6+ (testado com 3.13 no seu sistema).
Dependências:
bash

Recolher

Encapsular

Copiar
pip install python-binance requests
Opcional para análise técnica:
bash

Recolher

Encapsular

Copiar
pip install pandas ta
Chaves da API: Configuradas em config.py para produção e testnet.
Como Executar
Certifique-se de estar no diretório correto:
bash

Recolher

Encapsular

Copiar
cd "/Users/leovieira/Downloads/UltraBot_5.2 backtester"
Execute o script:
bash

Recolher

Encapsular

Copiar
/usr/local/bin/python3 main.py
Para modo real:
Edite config.py e defina DRY_RUN = False.
Exemplo de Saída
text

Recolher

Encapsular

Copiar
2025-04-10 02:47:25,268 - INFO - Bot inicializado em modo DRY RUN
2025-04-10 02:47:25,546 - INFO - [ICEBERG] Order book obtido para XRPUSDT: 1963383
2025-04-10 02:47:25,900 - INFO - [DELTA] Delta volume calculado para XRPUSDT: 126918.0
2025-04-10 02:47:26,220 - INFO - [SENTIMENTO] Open Interest para XRPUSDT: {'symbol': 'XRPUSDT', 'openInterest': '187537836.5', 'time': 1744264042268}
2025-04-10 02:47:26,535 - INFO - [SENTIMENTO] Funding Rate para XRPUSDT: [{'symbol': 'XRPUSDT', 'fundingTime': 1744243200000, 'fundingRate': '0.00007437', 'markPrice': '2.05240000'}]
2025-04-10 02:47:26,808 - INFO - ┌──────────────────────────────────────────────────┐
│ [ULTRABOT] Sinal Gerado - 2025-04-10 02:47:26    │
│ Par: XRPUSDT                                   │
│ Timeframe: 15m                                    │
│ Direção: N/A                                     │
│ Preço Atual: 2.0037                              │
│ Score Total: 10 (Baixo)                       │
│ Timeframes Analisados: 15m, 1h, 2h, 4h          │
├─ Resultado ────────────────────────────────────┤
│ ❌ Sinal Recusado - Menos de 2 TFs alinhados ou scores < 50│
│ Ação: Não Executado                  │
└──────────────────────────────────────────────────┘
Conclusão
O UltraBot 5.2 Backtester é uma base sólida para um bot de trading automatizado. Ele resolveu os problemas iniciais de importação e configuração, implementou coleta de dados em tempo real, e está pronto para expansões como análise técnica e execução de ordens. A engenharia por trás reflete boas práticas de modularidade, tratamento de erros, e integração com APIs externas.
