import socket
import threading
import urllib.parse
import json
import html
import os
import time
import ssl

lock = threading.Lock()
# Initialize from saved data if available
if os.path.exists('users.json'):
    with open('users.json', 'r') as f:
        users = json.load(f)
else:
    users = {}

if os.path.exists('sessions.json'):
    with open('sessions.json', 'r') as f:
        sessions = json.load(f)
else:
    sessions = {}

if os.path.exists('messages.json'):
    with open('messages.json', 'r') as f:
        messages = json.load(f)
else:
    messages = []

if os.path.exists('current_message_id.txt'):
    with open('current_message_id.txt', 'r') as f:
        current_message_id = int(f.read().strip())
else:
    current_message_id = 0

def parse_http_request(request):
    print(request)
    headers, body = request.split('\r\n\r\n', 1)
    headers = headers.split('\r\n')
    method, path, _ = headers[0].split()
    path, _, query_string = path.partition('?')
    headers = {k: v for k, v in (line.split(': ') for line in headers[1:])}
    return method, path, query_string, headers, body

def handle_client(client_socket):
    global users, sessions, messages, current_message_id
    request_data = client_socket.recv(1024).decode('utf-8')
    method, path, query_string, headers, body = parse_http_request(request_data)

    session_id = headers.get('Cookie', '').split('=')[-1]
    username = sessions.get(session_id)

    if method == 'POST' and path == '/login':
        params = dict(urllib.parse.parse_qsl(body))
        if not params.get('username') or not params.get('password'):
            response = 'HTTP/1.1 302 Found\r\nLocation: /login.html?error=2\r\n\r\n'  # error=2 for blank form
        elif users.get(params['username']) == params['password']:
            response = 'HTTP/1.1 302 Found\r\n'
            session_id = str(len(sessions))
            with lock:
                sessions[session_id] = params['username']
            response += 'Set-Cookie: session_id={}\r\n'.format(session_id)
            response += 'Location: /board.html\r\n\r\n'
        else:
            response = 'HTTP/1.1 302 Found\r\nLocation: /login.html?error=1\r\n\r\n'  # error=1 for incorrect username/password
    elif method == 'POST' and path == '/register':
        params = dict(urllib.parse.parse_qsl(body))
        if not params.get('username') or not params.get('password'):
            response = 'HTTP/1.1 302 Found\r\nLocation: /register.html?error=2\r\n\r\n'  # error=2 for blank form
        elif params['username'] not in users:
            with lock:
                users[params['username']] = params['password']
            response = 'HTTP/1.1 302 Found\r\nLocation: /login.html\r\n\r\n'
        else:
            response = 'HTTP/1.1 302 Found\r\nLocation: /register.html?error=1\r\n\r\n'  # error=1 for username already exists
    elif method == 'POST' and path == '/post_message':
        global current_message_id  # Make sure to declare this as global
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        params = dict(urllib.parse.parse_qsl(body))
        with lock:
            message = {
                'id': current_message_id,
                'username': username,
                'timestamp': timestamp,
                'content': html.escape(params.get('message', ''))
            }
            messages.append(message)
            current_message_id += 1  # Increment the message ID
        response = 'HTTP/1.1 302 Found\r\nLocation: /board.html\r\n\r\n'
    elif method == 'GET' and path == '/logout':
        if session_id in sessions:
            del sessions[session_id]
        response = 'HTTP/1.1 302 Found\r\nLocation: /login.html\r\n\r\n'
    elif method == 'GET' and path == '/get_messages':
        last_id = int(query_string.split('=')[-1]) if query_string else -1
        new_messages = [msg for msg in messages if msg['id'] > last_id]
        response = 'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n'
        response += json.dumps({'messages': new_messages})
    else:
        if not username and path not in ('/login.html', '/register.html'):
            response = 'HTTP/1.1 302 Found\r\nLocation: /login.html\r\n\r\n'
        else:
            if not path.startswith('/'):
                path = '/' + path
            if path == '/':
                path = '/login.html'
            try:
                with open(os.getcwd() + '/web' + path, 'r') as f:
                    content = f.read()
                    response = 'HTTP/1.1 200 OK\r\n'
                    if path.endswith('.html'):
                        response += 'Cache-Control: no-cache, no-store, must-revalidate\r\n'
                        response += 'Content-Type: text/html\r\n'
                    response += 'Content-Length: {}\r\n\r\n{}'.format(len(content), content)
            except FileNotFoundError:
                response = 'HTTP/1.1 404 Not Found\r\n\r\n'

    if method == 'POST' and path in ('/login', '/register', '/post_message', '/logout'):
        # Save users, sessions, and messages to their respective files after modification
        with lock:
            with open('users.json', 'w') as f:
                json.dump(users, f)
            with open('sessions.json', 'w') as f:
                json.dump(sessions, f)
            with open('messages.json', 'w') as f:
                json.dump(messages, f)
            with open('current_message_id.txt', 'w') as f:
                f.write(str(current_message_id))
    
    client_socket.sendall(response.encode('utf-8'))
    client_socket.close()

def start_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(('localhost', 8080))
    server_socket.listen(5)
    print("Server is listening on port", 8080)

     # Wrap the server socket with SSL
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(certfile='server.crt', keyfile='server.key')  # Load your certificate and private key
    ssl_server_socket = context.wrap_socket(server_socket, server_side=True)

    while True:
        try:
            client_socket, client_address = ssl_server_socket.accept()
            client_thread = threading.Thread(target=handle_client, args=(client_socket,))
            client_thread.start()
        except:
            pass

if __name__ == '__main__':
    start_server()
