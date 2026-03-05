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


@app.route('/api/set-token', methods=['POST'])
def set_token():
    data = request.get_json() or {}
    token = data.get('token', '').strip()
    if token.lower().startswith('bearer '):
        token = token[7:].strip()
    if not token:
        return jsonify({'error': 'Token is required'}), 400
    try:
        resp = req.get(
            f'{XIQ_BASE}/devices',
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
            params={'page': 1, 'limit': 1},
            timeout=15
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 502
    if resp.status_code == 401:
        return jsonify({'error': 'Token is invalid or expired'}), 401
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

    all_accounts = []

    # Fetch home accounts
    try:
        resp = req.get(f'{XIQ_BASE}/account/home-accounts', headers=h, timeout=15)
        if resp.status_code == 401:
            return jsonify({'error': 'Session expired'}), 401
        if resp.status_code == 200:
            body = resp.json()
            home = body.get('data', body if isinstance(body, list) else [])
            for a in home:
                a['_account_type'] = 'home'
            all_accounts.extend(home)
    except Exception:
        pass

    # Fetch managed/partner accounts (paginated)
    try:
        page, limit = 1, 100
        while True:
            resp = req.get(
                f'{XIQ_BASE}/account/managed-accounts',
                headers=h,
                params={'page': page, 'limit': limit},
                timeout=15
            )
            if resp.status_code != 200:
                break
            body = resp.json()
            managed = body.get('data', [])
            for a in managed:
                a['_account_type'] = 'managed'
            all_accounts.extend(managed)
            total = body.get('total_count', body.get('totalCount', len(managed)))
            if len(managed) < limit or sum(1 for a in all_accounts if a.get('_account_type') == 'managed') >= total:
                break
            page += 1
    except Exception:
        pass

    return jsonify({'data': all_accounts, 'total_count': len(all_accounts)}), 200


@app.route('/api/debug/accounts')
def debug_accounts():
    """Probes VHM-based and other paths to find tenant/VIQ listing endpoints."""
    h = _headers()
    if not h:
        return jsonify({'error': 'Not authenticated'}), 401

    # First fetch /account/viq to get the vhm_id
    vhm_id = None
    try:
        r = req.get(f'{XIQ_BASE}/account/viq', headers=h, timeout=10)
        if r.status_code == 200:
            vhm_id = r.json().get('vhm_id')
    except Exception:
        pass

    candidates = [
        '/account/viq',
        f'/vhm/{vhm_id}/customers' if vhm_id else None,
        f'/vhm/{vhm_id}/accounts' if vhm_id else None,
        f'/vhm/{vhm_id}/viq' if vhm_id else None,
        f'/account/vhm/{vhm_id}/customers' if vhm_id else None,
        f'/account/vhm/{vhm_id}' if vhm_id else None,
        '/account/vhm',
        '/account/switch',
        '/account/viq/list',
        '/account/viq/switch',
        '/vhm/customers',
        '/vhm/switch',
        '/mssp/customers',
        '/mssp/accounts',
        '/partner/accounts',
        '/partner/customers',
    ]
    candidates = [c for c in candidates if c]

    result = {'vhm_id_found': vhm_id, 'probes': {}}
    for path in candidates:
        try:
            resp = req.get(
                f'{XIQ_BASE}{path}',
                headers=h,
                params={'page': 1, 'limit': 10},
                timeout=10
            )
            ct = resp.headers.get('content-type', '')
            if 'json' in ct:
                body = resp.json()
            else:
                body = resp.text[:200]
            result['probes'][path] = {'status': resp.status_code, 'body': body}
        except Exception as e:
            result['probes'][path] = {'error': str(e)}

    return jsonify(result), 200


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
