#!/bin/bash

# Script de deploy para UltraBot Dashboard v1
# Atualizado para nova droplet em 15 de abril de 2025

echo "====== Iniciando deploy do UltraBot Dashboard ======"
echo "Data: $(date)"

# Diretório do projeto (ajustado para nova estrutura)
PROJECT_DIR=~/ultrabot-dashboard-v1/ultrabot-dashboard-v1

# Verificar se o diretório existe
if [ ! -d "$PROJECT_DIR" ]; then
    echo "Erro: Diretório do projeto não encontrado: $PROJECT_DIR"
    exit 1
fi

# Entrar no diretório do projeto
cd $PROJECT_DIR

# Instalar dependências do sistema (caso seja uma droplet nova)
echo "Instalando dependências do sistema..."
apt update && apt install -y python3 python3-pip git

# Atualizar o código do repositório Git
echo "Atualizando o código do repositório..."
git pull origin main

# Instalar ou atualizar dependências Python
echo "Atualizando dependências Python..."
pip3 install -r requirements.txt

# Reiniciar serviços relacionados
echo "Reiniciando serviços..."

# Verificar se o Streamlit está rodando e reiniciar
if pgrep -f "streamlit run dashboard.py" > /dev/null; then
    echo "Interrompendo serviço Streamlit..."
    pkill -f "streamlit run dashboard.py"
fi

# Iniciar o Streamlit em segundo plano
echo "Iniciando o serviço Streamlit..."
nohup streamlit run dashboard.py --server.port 8580 > streamlit.log 2>&1 &

sleep 5

echo "Verificando status do serviço..."
if pgrep -f "streamlit run dashboard.py" > /dev/null; then
    echo "Serviço Streamlit iniciado com sucesso!"
    echo "O dashboard está disponível em: http://209.38.100.245:8580"
else
    echo "ERRO: Falha ao iniciar o serviço Streamlit. Verifique o arquivo streamlit.log para mais detalhes."
    exit 1
fi

echo "====== Deploy concluído com sucesso! ======"