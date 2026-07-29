"""
Mafia Network Analyzer - Flask Backend
Analyzes criminal networks using NetworkX centrality measures
Auth: MongoDB Sign Up / Sign In with bcrypt password hashing
"""

import os
import json
import uuid
import traceback
import functools
import pandas as pd
import networkx as nx
import plotly.graph_objects as go
from flask import (Flask, render_template, request, jsonify,
                   session, redirect, url_for, flash)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

# ─────────────────────────────────────────────
# App Configuration
# ─────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY')

if not app.secret_key:
    raise RuntimeError("SECRET_KEY environment variable is required")
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

ALLOWED_EXTENSIONS = {'csv'}
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ─────────────────────────────────────────────
# MongoDB Setup
# ─────────────────────────────────────────────
MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/')
client = MongoClient(MONGO_URI)
db = client['mafia_analyzer']
users_col = db['users']
# Unique index on username and email
users_col.create_index('username', unique=True)
users_col.create_index('email', unique=True)


# ─────────────────────────────────────────────
# Auth helpers
# ─────────────────────────────────────────────
def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ─────────────────────────────────────────────
# Auth Routes
# ─────────────────────────────────────────────
@app.route('/')
def root():
    if 'user_id' in session:
        return redirect(url_for('index'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        data = request.get_json(silent=True) or request.form
        action = data.get('action', 'signin')

        if action == 'signup':
            username = (data.get('username') or '').strip()
            email    = (data.get('email') or '').strip().lower()
            password = data.get('password') or ''

            if not username or not email or not password:
                return jsonify({'error': 'All fields are required.'}), 400
            if len(password) < 6:
                return jsonify({'error': 'Password must be at least 6 characters.'}), 400

            hashed = generate_password_hash(password)
            try:
                result = users_col.insert_one({
                    'username': username,
                    'email': email,
                    'password': hashed,
                })
                session['user_id']  = str(result.inserted_id)
                session['username'] = username
                return jsonify({'success': True, 'redirect': url_for('index')})
            except DuplicateKeyError:
                return jsonify({'error': 'Username or email already exists.'}), 409

        else:  # signin
            identifier = (data.get('identifier') or '').strip()
            password   = data.get('password') or ''

            if not identifier or not password:
                return jsonify({'error': 'Username/email and password are required.'}), 400

            user = users_col.find_one(
                {'$or': [{'username': identifier}, {'email': identifier.lower()}]}
            )
            if not user or not check_password_hash(user['password'], password):
                return jsonify({'error': 'Invalid credentials. Try again.'}), 401

            session['user_id']  = str(user['_id'])
            session['username'] = user['username']
            return jsonify({'success': True, 'redirect': url_for('index')})

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ─────────────────────────────────────────────
# Main App Routes (protected)
# ─────────────────────────────────────────────
@app.route('/analyzer')
@login_required
def index():
    return render_template('index.html', username=session.get('username'))


@app.route('/upload', methods=['POST'])
@login_required
def upload():
    if 'file' not in request.files:
        return jsonify({"error": "No file part in request."}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected."}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "Only CSV files are allowed."}), 400

    filename = secure_filename(f"{uuid.uuid4()}_{file.filename}")
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    try:
        result = analyze_network(filepath)
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)


@app.route('/result')
@login_required
def result():
    return render_template('result.html', username=session.get('username'))


@app.route('/sample-csv')
@login_required
def sample_csv():
    csv_content = (
        "Source,Target\n"
        "Don_Corleone,Sonny\nDon_Corleone,Tom_Hagen\nDon_Corleone,Fredo\n"
        "Don_Corleone,Michael\nSonny,Clemenza\nSonny,Luca_Brasi\nSonny,Carlo\n"
        "Michael,Neri\nMichael,Clemenza\nMichael,Barzini\nMichael,Roth\n"
        "Tom_Hagen,Woltz\nTom_Hagen,Jack_Woltz\nClemenza,Paulie\nClemenza,Rocco\n"
        "Fredo,Roth\nFredo,Las_Vegas\nNeri,Fabrizio\nBarzini,Tattaglia\n"
        "Barzini,Sollozzo\nSollozzo,Virgil\nSollozzo,McCluskey\nRoth,Ola\n"
        "Roth,Duvall\nTattaglia,Bruno\n"
    )
    from flask import Response
    return Response(
        csv_content,
        mimetype='text/csv',
        headers={"Content-Disposition": "attachment; filename=sample_network.csv"}
    )


# ─────────────────────────────────────────────
# Network Analysis
# ─────────────────────────────────────────────
def analyze_network(filepath):
    df = pd.read_csv(filepath)
    required_cols = {'Source', 'Target'}
    if not required_cols.issubset(df.columns):
        df.columns = [c.strip().title() for c in df.columns]
        if not required_cols.issubset(df.columns):
            raise ValueError("CSV must have 'Source' and 'Target' columns.")

    df = df.dropna(subset=['Source', 'Target'])
    df['Source'] = df['Source'].astype(str).str.strip()
    df['Target'] = df['Target'].astype(str).str.strip()

    G = nx.from_pandas_edgelist(df, source='Source', target='Target',
                                create_using=nx.Graph())

    if len(G.nodes) == 0:
        raise ValueError("Graph has no nodes. Check your CSV.")

    node_count = len(G.nodes)
    edge_count = len(G.edges)

    degree_cent      = nx.degree_centrality(G)
    betweenness_cent = nx.betweenness_centrality(G, normalized=True)

    try:
        eigenvector_cent = nx.eigenvector_centrality(G, max_iter=1000)
    except nx.PowerIterationFailedConvergence:
        eigenvector_cent = degree_cent.copy()

    all_nodes = list(G.nodes)
    scores = {}
    for node in all_nodes:
        d = degree_cent.get(node, 0)
        b = betweenness_cent.get(node, 0)
        e = eigenvector_cent.get(node, 0)
        scores[node] = round(0.3 * d + 0.3 * b + 0.4 * e, 6)

    ranked   = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    boss_node = ranked[0][0]
    top5 = [
        {
            "rank": i + 1,
            "node": node,
            "score": round(score, 4),
            "degree": round(degree_cent.get(node, 0), 4),
            "betweenness": round(betweenness_cent.get(node, 0), 4),
            "eigenvector": round(eigenvector_cent.get(node, 0), 4),
        }
        for i, (node, score) in enumerate(ranked[:5])
    ]

    pos = nx.spring_layout(G, seed=42, k=2.5)
    edge_x, edge_y = [], []
    for u, v in G.edges():
        x0, y0 = pos[u]; x1, y1 = pos[v]
        edge_x += [x0, x1, None]; edge_y += [y0, y1, None]

    edge_trace = go.Scatter(
        x=edge_x, y=edge_y, mode='lines',
        line=dict(width=1.2, color='rgba(180,50,50,0.35)'),
        hoverinfo='none', showlegend=False
    )

    top5_nodes  = set(n for n, _ in ranked[:5])
    other_nodes = [n for n in all_nodes if n not in top5_nodes]

    def make_node_trace(nodes, color, size, symbol, name, border='rgba(255,255,255,0.6)'):
        return go.Scatter(
            x=[pos[n][0] for n in nodes], y=[pos[n][1] for n in nodes],
            mode='markers+text',
            marker=dict(size=size, color=color,
                        line=dict(width=2, color=border), symbol=symbol),
            text=[str(n) for n in nodes], textposition='top center',
            textfont=dict(size=10, color='#e0e0e0', family='Courier New'),
            hovertext=[
                f"<b>{n}</b><br>Score: {scores[n]:.4f}<br>"
                f"Degree: {degree_cent[n]:.4f}<br>"
                f"Betweenness: {betweenness_cent[n]:.4f}<br>"
                f"Eigenvector: {eigenvector_cent[n]:.4f}"
                for n in nodes
            ],
            hoverinfo='text', name=name,
        )

    traces = [edge_trace]
    traces.append(make_node_trace([boss_node], '#ff2244', 36, 'star', 'Boss Node', border='#ffcc00'))
    top5_except_boss = [n for n in list(top5_nodes)[:5] if n != boss_node]
    if top5_except_boss:
        traces.append(make_node_trace(top5_except_boss, '#ff6600', 22, 'diamond', 'Top Influencers', border='#ff9900'))
    if other_nodes:
        traces.append(make_node_trace(other_nodes, '#3a4a6b', 14, 'circle', 'Network Nodes', border='rgba(100,130,200,0.5)'))

    layout = go.Layout(
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#e0e0e0'), showlegend=True,
        legend=dict(font=dict(size=12, color='#ccc'),
                    bgcolor='rgba(20,20,30,0.8)',
                    bordercolor='rgba(180,50,50,0.5)', borderwidth=1),
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        hovermode='closest',
    )

    fig = go.Figure(data=traces, layout=layout)
    stats = {
        "node_count": node_count, "edge_count": edge_count,
        "density": round(nx.density(G), 4),
        "components": nx.number_connected_components(G),
        "avg_degree": round(sum(dict(G.degree()).values()) / node_count, 2),
    }
    return {
        "boss_node": boss_node, "boss_score": round(scores[boss_node], 4),
        "top5": top5, "graph_json": fig.to_json(), "stats": stats,
    }


# ─────────────────────────────────────────────
# Run
# ─────────────────────────────────────────────
if __name__ == '__main__':
    port = int(os.environ.get('PORT', '5000'))

    print("=" * 60)
    print("Mafia Network Analyzer")
    print(f"Running on port {port}")
    print("=" * 60)

    app.run(
        host='0.0.0.0',
        port=port,
        debug=False
    )
