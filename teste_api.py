from binance.client import Client

api_key = "1O15N1tPBT2knz0QvXuW7VyN6jW8ci3xQFWM5f6IicqcFMhtxA4hJIo97KQNSTTx"  # Substitua pela DRY_RUN_API_KEY
api_secret = "LWrfZ7OkWxc6Tx0ZuoCgkZyYVwpcBqIbTq9qCTMRI0m1Cr16c39skQ0RLfrNZgwB"  # Substitua pela DRY_RUN_API_SECRET

client = Client(api_key, api_secret, testnet=True)
try:
    perms = client.get_account_api_permissions()
    print("Chave válida! Permissões:", perms)
except Exception as e:
    print("Erro:", e)