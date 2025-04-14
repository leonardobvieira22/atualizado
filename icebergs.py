
from binance.client import Client
import os

api_key = os.getenv("BINANCE_API_KEY")
api_secret = os.getenv("BINANCE_API_SECRET")
client = Client(api_key, api_secret)

def detectar_iceberg(par, preco_atual, lado='compra', profundidade=5, threshold=30000):
    try:
        book = client.get_order_book(symbol=par.replace("/", ""), limit=profundidade)
        if lado == 'compra':
            for preco, qtd in book['asks']:  # ofertas de venda
                preco = float(preco)
                qtd = float(qtd)
                if preco > preco_atual and qtd * preco >= threshold:
                    return True  # iceberg de venda acima
        elif lado == 'venda':
            for preco, qtd in book['bids']:  # ofertas de compra
                preco = float(preco)
                qtd = float(qtd)
                if preco < preco_atual and qtd * preco >= threshold:
                    return True  # iceberg de compra abaixo
        return False
    except Exception as e:
        print(f"[ICEBERG] Erro ao verificar order book: {e}")
        return False
