from flask import Flask, render_template, request, redirect, url_for, Response, session
from functools import wraps
import os
import csv
import xml.etree.ElementTree as ET
import re

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")


def check_auth(username, password):
    """Проверка логина и пароля"""
    return username == USERNAME and password == PASSWORD


def authenticate():
    """Запрос авторизации"""
    return Response(
        "Требуется авторизация",
        401,
        {"WWW-Authenticate": 'Basic realm="Login Required"'},
    )


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)

    return decorated


def load_clients():
    """Загрузка всех клиентов из всех CSV-файлов из папки data/"""
    clients = []
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    for filename in os.listdir(data_dir):
        if filename.endswith(".csv"):
            with open(os.path.join(data_dir, filename), encoding="utf-8") as f:
                reader = csv.reader(f, delimiter=";")
                for row in reader:
                    if len(row) > 1:
                        clients.append(
                            {"id": row[0].strip(), "fio": row[1].strip(), "data": row}
                        )
    return clients


def get_first_letters():
    """Возвращает отсортированный список уникальных первых букв фамилий всех клиентов"""
    letters = set()
    for client in load_clients():
        fio = client["fio"]
        if fio:
            first_letter = fio.strip()[0].upper()
            if re.match(r"[А-ЯA-Z]", first_letter):
                letters.add(first_letter)
    return sorted(letters)


def filter_clients_by_letter(clients, letter):
    """Фильтрует клиентов по первой букве фамилии"""
    if not letter:
        return clients
    return [c for c in clients if c["fio"].strip().upper().startswith(letter.upper())]


def search_clients(query, clients):
    """Поиск клиентов по ФИО или ID внутри уже отфильтрованного списка"""
    query = query.lower()
    results = []
    for client in clients:
        if query in client["fio"].lower() or query in client["id"]:
            results.append(client)
    return results


def partial_parse_xml(path):
    """Пытается извлечь как можно больше данных из повреждённого XML-файла"""
    history = []
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
        
        content = re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;)", "&amp;", content)
        
        root = ET.fromstring(content)
        for elem in root.iter():
            history.append({child.tag: child.text for child in elem})
    except Exception as e:
        history.append({"Ошибка": f"Частичный парсинг: {str(e)}"})
    return history


def load_credit_history(client_id, fio):
    """Загрузка истории кредитов по ID клиента и ФИО (ищем xml-файл в папках data/history/Х/)"""
    first_letter = fio.strip()[0].upper()
    folder = os.path.join(os.path.dirname(__file__), "data", "history", first_letter)
    if not os.path.exists(folder):
        return []
    for filename in os.listdir(folder):
        if filename.startswith(client_id + "_") and filename.endswith(".xml"):
            path = os.path.join(folder, filename)
            try:
                tree = ET.parse(path)
                root = tree.getroot()
                history = []
                for elem in root.iter():
                    history.append({child.tag: child.text for child in elem})
                return history
            except Exception as e:
                
                partial = partial_parse_xml(path)
                partial.append(
                    {
                        "Ошибка": f"Файл повреждён: {str(e)} (файл: {filename})",
                        "Рекомендация": "Проверьте корректность XML-файла. Возможно, есть неэкранированные спецсимволы или битая структура.",
                    }
                )
                return partial
    return []


@app.route("/")
@requires_auth
def index():
    query = request.args.get("q", "")
    page = int(request.args.get("page", 1))
    per_page = 30 
    letter = request.args.get("letter", "")
    all_clients = load_clients()
    letters = get_first_letters()
    filtered_clients = filter_clients_by_letter(all_clients, letter)
    clients = search_clients(query, filtered_clients) if query else filtered_clients
    total = len(clients)
    start = (page - 1) * per_page
    end = start + per_page
    clients_page = clients[start:end]
    total_pages = (total + per_page - 1) // per_page
    return render_template(
        "index.html",
        clients=clients_page,
        query=query,
        page=page,
        total_pages=total_pages,
        letters=letters,
        selected_letter=letter,
    )


@app.route("/client/<client_id>")
@requires_auth
def client_detail(client_id):
    client = next((c for c in load_clients() if c["id"] == client_id), None)
    if not client:
        return "Клиент не найден", 404
    history = load_credit_history(client_id, client["fio"])
    return render_template("client.html", client=client, history=history)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
