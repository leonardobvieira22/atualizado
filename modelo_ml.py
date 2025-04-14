
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix
import joblib
import os

MODELO_PATH = 'modelo_sinais_rf.pkl'

# Treina o modelo a partir do histórico de sinais
def treinar_modelo(caminho_csv='sinais_detalhados.csv'):
    if not os.path.exists(caminho_csv):
        print('[ML] Arquivo de sinais detalhados não encontrado.')
        return

    df = pd.read_csv(caminho_csv)

    # Considera sucesso se lucro percentual > 0
    df['sucesso'] = df['lucro_percentual'].apply(lambda x: 1 if x > 0 else 0)

    colunas_utilizadas = [
        'rsi', 'adx', 'ema_curta', 'ema_longa', 'swing_high', 'swing_low',
        'volume', 'ia_score', 'score_tecnico'
    ]

    df = df.dropna(subset=colunas_utilizadas + ['sucesso'])

    X = df[colunas_utilizadas]
    y = df['sucesso']

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    clf = RandomForestClassifier(n_estimators=100, random_state=42)
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)

    print('[ML] Avaliação do modelo:')
    print(classification_report(y_test, y_pred))
    print(confusion_matrix(y_test, y_pred))

    joblib.dump(clf, MODELO_PATH)
    print('[ML] Modelo salvo em', MODELO_PATH)


# Usa o modelo para prever a chance de sucesso de um novo sinal
def classificar_sinal(dados):
    if not os.path.exists(MODELO_PATH):
        print('[ML] Modelo não encontrado. Treine primeiro com treinar_modelo().')
        return None

    clf = joblib.load(MODELO_PATH)

    entrada = pd.DataFrame([{
        'rsi': dados.get('rsi', 0),
        'adx': dados.get('adx', 0),
        'ema_curta': dados.get('ema_curta', 0),
        'ema_longa': dados.get('ema_longa', 0),
        'swing_high': dados.get('swing_high', 0),
        'swing_low': dados.get('swing_low', 0),
        'volume': dados.get('volume', 0),
        'ia_score': dados.get('ia_score', 0),
        'score_tecnico': dados.get('score_tecnico', 0)
    }])

    prob = clf.predict_proba(entrada)[0][1]  # Probabilidade de sucesso
    return prob
