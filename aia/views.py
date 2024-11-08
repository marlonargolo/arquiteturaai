import json
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
import requests
from openai import OpenAI
from django.shortcuts import render, redirect
from .models import Message
import mercadopago
from django.contrib.auth.decorators import login_required

# Variáveis sensíveis centralizadas
WHATSAPP_API_URL = 'https://graph.facebook.com/v20.0/418446388022428/messages'
ACCESS_TOKEN = ''
VERIFY_TOKEN = 'hsdfbvhbsd2458@hvb'
OPENAI_API_KEY = ''
MP_ACCESS_TOKEN = ''
MP_PUBLIC_KEY = ''

# Variável para armazenar IDs de mensagens já processadas (idealmente, isso seria um banco de dados)
processed_message_ids = set()
mp = mercadopago.SDK(MP_ACCESS_TOKEN)  # iniciar mercado pago


def create_preference(request):
    # Crie a preferência de pagamento com as informações do item e opções
    preference_data = {
        "items": [
            {
                "title": "Produto Exemplo",
                "quantity": 1,
                "currency_id": "BRL",
                "unit_price": 100.00
            }
        ],
        "back_urls": {
            "success": "http://www.seusite.com/pagamento/sucesso",
            "failure": "http://www.seusite.com/pagamento/erro",
            "pending": "http://www.seusite.com/pagamento/pendente"
        },
        "auto_return": "approved",
        "notification_url": "http://www.seusite.com/notificacoes/"
    }

    preference_response = mp.preference().create(preference_data)
    preference = preference_response["response"]

    # Redirecione o usuário para o URL de checkout do Mercado Pago
    return redirect(preference['init_point'])


def payment_success(request):
    return render(request, 'payment_success.html')


def payment_failure(request):
    return render(request, 'payment_failure.html')


def payment_pending(request):
    return render(request, 'payment_pending.html')


@csrf_exempt
def notification_handler(request):
    if request.method == 'POST':
        notification_data = json.loads(request.body)
        payment_id = notification_data.get("data", {}).get("id")

        if payment_id:
            # Recupere o pagamento no Mercado Pago para verificar o status
            payment = mp.payment().get(payment_id)
            payment_status = payment["response"].get("status")

            # Atualize o status do pedido no banco de dados (omissão de código de exemplo)

        return JsonResponse({'status': 'notificação recebida'}, status=200)

    return JsonResponse({'status': 'método não permitido'}, status=405)


@csrf_exempt
def webhook(request):
    if request.method == 'GET':
        verify_token = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge')

        if verify_token == VERIFY_TOKEN:
            return HttpResponse(challenge, status=200)
        else:
            return HttpResponse('Erro de verificação do token.', status=403)

    elif request.method == 'POST':
        try:
            incoming_message = json.loads(request.body.decode('utf-8'))
            entry = incoming_message.get('entry', [])
            if not entry:
                return JsonResponse({'status': 'ignored', 'message': "'entry' não encontrado"}, status=200)

            changes = entry[0].get('changes', [])
            if not changes:
                return JsonResponse({'status': 'ignored', 'message': "'changes' não encontrado"}, status=200)

            value = changes[0].get('value', {})
            if 'messages' not in value:
                return JsonResponse({'status': 'ignored', 'message': "'messages' não encontrado"}, status=200)

            message = value['messages'][0]
            from_number = message.get('from')
            message_body = message.get('text', {}).get('body')

            Message.objects.create(sender=from_number, body=message_body, direction='received')

            if not message_body:
                raise KeyError("'body' não encontrado na mensagem")

            print(f"Mensagem recebida de {from_number}: {message_body}")

            if "criador de conteúdo" in message_body.lower():
                role = "criador_de_conteudo"
            elif "acompanhamento profissional" in message_body.lower():
                role = "acompanhamento_profissional"
            else:
                role = "atendente"

            response_message = get_chatgpt_response(message_body, role)
            Message.objects.create(sender='bot', body=response_message, direction='sent')

            send_message(from_number, response_message)

            return JsonResponse({'status': 'success'}, status=200)

        except (KeyError, IndexError, json.JSONDecodeError) as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    return JsonResponse({'status': 'Method not allowed'}, status=405)


def send_message(to_number, message):
    headers = {
        'Authorization': f'Bearer {ACCESS_TOKEN}',
        'Content-Type': 'application/json'
    }

    data = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {
            "body": message
        }
    }

    response = requests.post(WHATSAPP_API_URL, headers=headers, json=data)
    if response.status_code == 200:
        print(f"Mensagem enviada para {to_number}: {message}")
        return response.json()
    else:
        print(f"Erro ao enviar mensagem para {to_number}: {response.text}")
        return {'status': 'error', 'message': response.text}


def get_chatgpt_response(user_message, role):
    client = OpenAI(api_key=OPENAI_API_KEY)
    try:
        roles = {
            "atendente": "Você é um atendente virtual, pronto para responder perguntas de clientes e resolver suas dúvidas.",
            "criador_de_conteudo": "Você é um criador de conteúdo criativo, capaz de produzir textos envolventes, posts para redes sociais, e artigos.",
            "acompanhamento_profissional": "Você é um mentor especializado em acompanhamento profissional, oferecendo conselhos sobre carreira, produtividade e desenvolvimento pessoal."
        }

        system_message = roles.get(role, "Você é um assistente útil.")

        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            max_tokens=150,
            temperature=0.7
        )

        chat_response = response.choices[0].text.strip()
        return chat_response

    except Exception as e:
        return f"Erro ao gerar resposta: {str(e)}"


def get_messages(request):
    messages = Message.objects.all().order_by('timestamp')
    messages_data = [{"sender": msg.sender, "body": msg.body, "direction": msg.direction, "timestamp": msg.timestamp}
                     for msg in messages]
    return JsonResponse(messages_data, safe=False)


@login_required
def home(request):
    return render(request, 'home.html')


def index(request):
    return render(request, 'index.html')


@login_required
def cadastro(request):
    return render(request, 'cadastro.html')


@login_required
def perfil(request):
    return render(request, 'perfil.html')


@login_required
def chat(request):
    return render(request, 'chat.html')

