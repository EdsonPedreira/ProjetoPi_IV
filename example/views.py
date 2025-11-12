# example/views.py

import json
from datetime import datetime, timedelta
from django.db.models.functions import TruncDate
from django.shortcuts import render, redirect
from django.db.models import Sum
from django.utils.safestring import mark_safe
import pandas as pd
import numpy as np
from .models import Arrecadacao, Arrecadacao_eletrodomestico, Arrecadacao_alimento, Vestuario, Eletrodomestico, \
    Alimento, Tamanho, Genero, Arrecadador


def treinar_e_prever_doacoes(model_class, look_back=1, future_steps=30):
    # 1. Obter os dados do banco de dados do Django
    doacoes_db = list(model_class.objects.order_by('criacao').values('criacao').annotate(total=Sum('quantidade')))

    if len(doacoes_db) < 2:
        return [], []

    df = pd.DataFrame(doacoes_db)
    data = df[['total']].values.astype('float32')

    # Normalize os dados
    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled_data = scaler.fit_transform(data)

    def create_dataset(dataset, look_back=1):
        X, Y = [], []
        for i in range(len(dataset) - look_back):
            a = dataset[i:(i + look_back), 0]
            X.append(a)
            Y.append(dataset[i + look_back, 0])
        return np.array(X), np.array(Y)

    X, y = create_dataset(scaled_data, look_back)
    X = np.reshape(X, (X.shape[0], 1, X.shape[1]))

    # 2. Construir e treinar o modelo
    model = tf.keras.models.Sequential()
    model.add(tf.keras.layers.LSTM(4, input_shape=(1, look_back)))
    model.add(tf.keras.layers.Dense(1))
    model.compile(loss='mean_squared_error', optimizer='adam')
    model.fit(X, y, epochs=100, batch_size=1, verbose=0)

    # 3. Fazer a previsão de N passos futuros
    last_known_data = scaled_data[-look_back:]
    future_predictions = []

    for _ in range(future_steps):
        input_data = np.reshape(last_known_data, (1, 1, look_back))
        prediction_scaled = model.predict(input_data, verbose=0)
        future_predictions.append(prediction_scaled[0][0])

        # Usa a nova previsão como entrada para a próxima previsão
        last_known_data = np.append(last_known_data[1:], prediction_scaled)

    # Inverter a normalização para obter os valores reais
    future_predictions_array = np.array(future_predictions).reshape(-1, 1)
    predictions_real = scaler.inverse_transform(future_predictions_array)

    # Arredondar para o número inteiro mais próximo
    predictions_real = [int(round(p[0])) for p in predictions_real]

    return predictions_real


def index(request):
    # Soma das quantidades de vestuário
    soma_quantidade = Arrecadacao.objects.aggregate(total=Sum('quantidade'))['total'] or 0

    # Soma das quantidades de eletrodomésticos
    soma_quantidade_eletrodomestico = Arrecadacao_eletrodomestico.objects.aggregate(total=Sum('quantidade'))[
                                          'total'] or 0

    # Soma das quantidades de alimentos
    soma_quantidade_alimento = Arrecadacao_alimento.objects.aggregate(total=Sum('quantidade'))['total'] or 0

    context = {
        'soma_quantidade': soma_quantidade,
        'soma_quantidade_eletrodomestico': soma_quantidade_eletrodomestico,
        'soma_quantidade_alimento': soma_quantidade_alimento,
    }
    return render(request, 'index.html', context)


def grafico_view(request):
    # Lógica de extração de dados para o gráfico
    arrecadacoes_vestuario = Arrecadacao.objects.order_by('criacao')
    arrecadacoes_eletro = Arrecadacao_eletrodomestico.objects.order_by('criacao')
    arrecadacoes_alimento = Arrecadacao_alimento.objects.order_by('criacao')

    dates = []
    data_map = {}

    all_arrecadacoes = list(arrecadacoes_vestuario) + list(arrecadacoes_eletro) + list(arrecadacoes_alimento)
    all_arrecadacoes.sort(key=lambda x: x.criacao)

    for item in all_arrecadacoes:
        date_str = item.criacao.strftime('%Y-%m-%d')
        if date_str not in dates:
            dates.append(date_str)

        if date_str not in data_map:
            data_map[date_str] = {
                'vestuario': 0,
                'eletro': 0,
                'alimento': 0
            }

        # Determine o tipo de doação e adicione a quantidade
        if hasattr(item, 'vestuario'):
            data_map[date_str]['vestuario'] += item.quantidade
        elif hasattr(item, 'eletrodomestico'):
            data_map[date_str]['eletro'] += item.quantidade
        elif hasattr(item, 'alimento'):
            data_map[date_str]['alimento'] += item.quantidade

    vestuario_data = [data_map[date]['vestuario'] for date in dates]
    eletro_data = [data_map[date]['eletro'] for date in dates]
    alimento_data = [data_map[date]['alimento'] for date in dates]

    # Ajuste para lidar com listas de dados vazias
    if not dates:
        today = datetime.now().strftime('%Y-%m-%d')
        dates = [today]
        vestuario_data = [0]
        eletro_data = [0]
        alimento_data = [0]

    # Lógica de previsão mais robusta para lidar com listas vazias
    previsao_vestuario_data = vestuario_data + [vestuario_data[-1] + 5]
    previsao_eletro_data = eletro_data + [eletro_data[-1] + 3]
    previsao_alimento_data = alimento_data + [alimento_data[-1] + 7]

    # Assegura que o array de datas de previsão tenha um elemento a mais
    previsao_dates = dates + ["Previsão"]

    # Convertendo para JSON
    dates_json = json.dumps(previsao_dates)
    vestuario_data_json = json.dumps(vestuario_data)
    eletro_data_json = json.dumps(eletro_data)
    alimento_data_json = json.dumps(alimento_data)
    previsao_vestuario_data_json = json.dumps(previsao_vestuario_data)
    previsao_eletro_data_json = json.dumps(previsao_eletro_data)
    previsao_alimento_data_json = json.dumps(previsao_alimento_data)

    context = {
        'dates_json': dates_json,
        'vestuario_data_json': vestuario_data_json,
        'eletro_data_json': eletro_data_json,
        'alimento_data_json': alimento_data_json,
        'previsao_vestuario_data_json': previsao_vestuario_data_json,
        'previsao_eletro_data_json': previsao_eletro_data_json,
        'previsao_alimento_data_json': previsao_alimento_data_json,
    }
    return render(request, 'grafico.html', context)


# Funções de outras views
def adicionar_doacao(request):
    quantidade = 0
    if request.method == 'POST':
        tipo = request.POST.get('tipo')
        quantidade = int(request.POST.get('quantidade', 0))

        if tipo == 'vestuario':
            vestuario_id = request.POST.get('vestuario')
            tamanho_id = request.POST.get('tamanho')
            genero_id = request.POST.get('genero')

            vestuario = Vestuario.objects.get(id=vestuario_id)
            tamanho = Tamanho.objects.get(id=tamanho_id)
            genero = Genero.objects.get(id=genero_id)

            Arrecadacao.objects.create(
                vestuario=vestuario,
                tamanho=tamanho,
                genero=genero,
                quantidade=quantidade,
            )

        elif tipo == 'eletrodomestico':
            eletro_id = request.POST.get('eletrodomestico')
            eletro = Eletrodomestico.objects.get(id=eletro_id)

            Arrecadacao_eletrodomestico.objects.create(
                eletrodomestico=eletro,
                quantidade=quantidade,
            )

        elif tipo == 'alimento':
            alimento_id = request.POST.get('alimento')
            alimento = Alimento.objects.get(id=alimento_id)

            Arrecadacao_alimento.objects.create(
                alimento=alimento,
                quantidade=quantidade,
            )

        return render(request, 'adicionar_doacao.html', {'doacao_realizada': True, 'quantidade': quantidade})

    vestuarios = Vestuario.objects.all()
    eletrodomesticos = Eletrodomestico.objects.all()
    alimentos = Alimento.objects.all()
    tamanhos = Tamanho.objects.all()
    generos = Genero.objects.all()

    context = {
        'vestuarios': vestuarios,
        'eletrodomesticos': eletrodomesticos,
        'alimentos': alimentos,
        'tamanhos': tamanhos,
        'generos': generos,
    }
    return render(request, 'adicionar_doacao.html', context)


def cadastrar_arrecadador(request):
    if request.method == 'POST':
        nome = request.POST.get('nome')
        cep = request.POST.get('cep')
        # Bairro e cidade serão preenchidos automaticamente no signal
        Arrecadador.objects.create(nome=nome, cep=cep)
        return redirect('index')
    return render(request, 'adicionar_arrecadador.html')


def soma_quantidade_arrecadacao(request):
    soma = Arrecadacao.objects.aggregate(soma_quantidade=Sum('quantidade'))['soma_quantidade'] or 0
    context = {'soma_quantidade': soma}
    return render(request, 'soma_quantidade_arrecadacao.html', context)


def soma_quantidade_eletrodomestico(request):
    soma = Arrecadacao_eletrodomestico.objects.aggregate(soma_quantidade_eletrodomestico=Sum('quantidade'))[
               'soma_quantidade_eletrodomestico'] or 0
    context = {'soma_quantidade_eletrodomestico': soma}
    return render(request, 'index.html', context)