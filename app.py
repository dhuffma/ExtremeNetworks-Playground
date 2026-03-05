from flask import Flask, send_from_directory, request, jsonify, session
import os
import requests as req

app = Flask(__name__, static_folder='public')
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24).hex())

XIQ_BASE = 'https://api.extremecloudiq.com'


def _token():
    return session.get('xiq_token') or os.environ.get('XIQ_API_TOKEN', '').strip()


def _headers():
    token = _token()
    if not token:
        return None
    return {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}


def _paginate(path):
    """Fetch all pages from a XIQ list endpoint. Returns (list, status_code)."""
    all_items = []
    page = 1
    limit = 100
    owner_id = session.get('owner_id')
    while True:
        params = {'page': page, 'limit': limit}
        if owner_id:
            params['ownerId'] = owner_id
        try:
            resp = req.get(
                f'{XIQ_BASE}{path}',
                headers=_headers(),
                params=params,
                timeout=30
            )
        except Exception:
            return None, 502
        if resp.status_code == 401:
            return None, 401
        if resp.status_code != 200:
            return None, resp.status_code
        body = resp.json()
        items = body.get('data', [])
        all_items.extend(items)
        total = body.get('total_count', body.get('totalCount', len(items)))
        if len(all_items) >= total or len(items) < limit:
            break
        page += 1
    return all_items, 200


@app.route('/')
def index():
    return send_from_directory('public', 'index.html')


@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('public', path)


@app.route('/api/status')
def status():
    return jsonify({'configured': bool(_token())})


@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    try:
        resp = req.post(
            f'{XIQ_BASE}/login',
            json={'username': username, 'password': password},
            timeout=15
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 502
    if resp.status_code == 401:
        return jsonify({'error': 'Invalid username or password'}), 401
    if resp.status_code != 200:
        return jsonify({'error': f'Login failed ({resp.status_code})'}), resp.status_code
    token = resp.json().get('access_token')
    if not token:
        return jsonify({'error': 'No token returned from XIQ'}), 500
    session['xiq_token'] = token
    return jsonify({'ok': True})


@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('xiq_token', None)
    session.pop('owner_id', None)
    session.pop('account_name', None)
    return jsonify({'ok': True})


@app.route('/api/accounts')
def get_accounts():
    h = _headers()
    if not h:
        return jsonify({'error': 'Not authenticated'}), 401
    try:
        resp = req.get(f'{XIQ_BASE}/account/home-accounts', headers=h, timeout=15)
    except Exception as e:
        return jsonify({'error': str(e)}), 502
    if resp.status_code == 401:
        return jsonify({'error': 'Session expired'}), 401
    if resp.status_code != 200:
        return jsonify({'data': [], 'total_count': 0}), 200
    return jsonify(resp.json()), 200


@app.route('/api/select-account', methods=['POST'])
def select_account():
    data = request.get_json() or {}
    session['owner_id'] = data.get('owner_id')
    session['account_name'] = data.get('name', 'Home VIQ')
    return jsonify({'ok': True})


@app.route('/api/devices')
def get_devices():
    if not _token():
        return jsonify({'error': 'Not authenticated'}), 401
    items, status_code = _paginate('/devices')
    if items is None:
        return jsonify({'error': f'Failed to fetch devices (status {status_code})'}), status_code
    return jsonify({'data': items, 'total': len(items)})


@app.route('/api/clients')
def get_clients():
    if not _token():
        return jsonify({'error': 'Not authenticated'}), 401
    items, status_code = _paginate('/clients/active')
    if items is None:
        items, status_code = _paginate('/clients')
    if items is None:
        items = []
    return jsonify({'data': items, 'total': len(items)})


@app.route('/api/alarms')
def get_alarms():
    if not _token():
        return jsonify({'error': 'Not authenticated'}), 401
    owner_id = session.get('owner_id')
    params = {'page': 1, 'limit': 200, 'acknowledged': 'false'}
    if owner_id:
        params['ownerId'] = owner_id
    try:
        resp = req.get(f'{XIQ_BASE}/alarms', headers=_headers(), params=params, timeout=15)
    except Exception as e:
        return jsonify({'error': str(e)}), 502
    if resp.status_code != 200:
        return jsonify({'data': [], 'total': 0}), 200
    return jsonify(resp.json()), 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
