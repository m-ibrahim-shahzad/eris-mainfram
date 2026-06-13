from database import get_db_connection, init_db, global_rag_search
import os
import sqlite3
import uuid
import requests  # Clean standard library to securely dispatch our free AI calls
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from dotenv import load_dotenv
from authlib.integrations.flask_client import OAuth

# Load environmental variables
load_dotenv()

app = Flask(__name__)
app.secret_key = "eris_mainframe_secure_matrix_key_9918"

# --- HARDCODED CREDENTIALS CONFIGURATION MATRIX ---
# Paste your actual keys straight inside these quotes!
GOOGLE_CLIENT_ID = "YOUR_LONG_GOOGLE_ID_HERE.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET = "YOUR_LONG_GOOGLE_CLIENT_SECRET_HERE"
OPENROUTER_API_KEY = "YOUR_OPENRO"

# Initialize Google Authlib Handshake Client Matrix
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# Import our customized relational RAG storage functions
init_db()


# --- FRONTEND ROUTING VIEWS & AUTH LOOP ---

@app.route("/")
def index():
    if "user_profile" not in session:
        return render_template("login.html")
    return render_template("index.html")


@app.route("/login")
def login_redirect():
    redirect_uri = url_for('auth_callback', _external=True)
    if redirect_uri.startswith('http://') and '.ngrok' in redirect_uri:
        redirect_uri = redirect_uri.replace('http://', 'https://')
    return google.authorize_redirect(redirect_uri)


@app.route("/callback")
def auth_callback():
    try:
        token = google.authorize_access_token()
        user_info = token.get('userinfo')
        if user_info:
            session["user_profile"] = {
                "sub": user_info.get("sub"),
                "name": user_info.get("name"),
                "email": user_info.get("email")
            }
            session.permanent = True
    except Exception as e:
        print(f"OAuth loop authentication intercept failure: {str(e)}")
    return redirect("/")


@app.route("/login-mock")
def login_mock():
    session["user_profile"] = {
        "sub": "mock_google_user_12345",
        "name": "Eris Developer",
        "email": "dev@eris.ai"
    }
    return redirect("/")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# --- REST API SERVICE GATEWAY ENDPOINTS ---

@app.route("/api/history/clear", methods=["POST", "DELETE"])
def clear_all_user_history():
    if "user_profile" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    google_id = session["user_profile"]["sub"]
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM messages WHERE session_id IN (SELECT id FROM sessions WHERE google_id = ?)", (google_id,))
        cursor.execute(
            "DELETE FROM sessions WHERE google_id = ?", (google_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/history", methods=["GET"])
def get_user_chat_history():
    if "user_profile" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    google_id = session["user_profile"]["sub"]
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, title FROM sessions WHERE google_id = ? ORDER BY created_at DESC", (google_id,))
        rows = cursor.fetchall()
        conn.close()

        history = [{"id": row["id"], "title": row["title"]} for row in rows]
        return jsonify(history)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/session/<session_id>", methods=["GET"])
def get_chat_session_messages(session_id):
    if "user_profile" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY timestamp ASC", (session_id,))
        rows = cursor.fetchall()
        conn.close()

        messages = [{"role": row["role"], "content": row["content"]}
                    for row in rows]
        return jsonify({"messages": messages})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/session/<session_id>", methods=["DELETE"])
def delete_single_chat(session_id):
    if "user_profile" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM messages WHERE session_id = ?", (session_id,))
        cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/session/<session_id>/rename", methods=["POST"])
def rename_chat_session(session_id):
    if "user_profile" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    new_title = data.get("title", "Updated Chat")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE sessions SET title = ? WHERE id = ?",
                       (new_title, session_id))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/ask", methods=["POST"])
def process_ai_prompt():
    if "user_profile" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    google_id = session["user_profile"]["sub"]
    data = request.get_json()
    prompt = data.get("prompt", "").strip()
    session_id = data.get("session_id", "")

    if not prompt:
        return jsonify({"error": "Prompt string cannot be completely empty"}), 400

    # 1. Execute background RAG lookup matrix
    retrieved_longterm_memory = global_rag_search(google_id, prompt)

    conn = get_db_connection()
    cursor = conn.cursor()

    if not session_id:
        session_id = str(uuid.uuid4())
        auto_title = prompt[:22] + "..." if len(prompt) > 22 else prompt
        cursor.execute("INSERT INTO sessions (id, google_id, title) VALUES (?, ?, ?)",
                       (session_id, google_id, auto_title))

    # Save prompt to local history tracker
    cursor.execute(
        "INSERT INTO messages (session_id, role, content) VALUES (?, 'user', ?)", (session_id, prompt))

    # 2. Build system instruction prompt window
    system_instruction = (
        "You are Eris, a helpful and highly intelligent AI core running inside a dark mainframe console workspace.\n"
        "Respond clearly using clean markdown formatting. Below is background data retrieved from the user's past chats.\n"
        "If it's relevant, naturally weave it into your response without saying things like 'RAG context applied'.\n\n"
        f"[Historical Core Background Memory]:\n{retrieved_longterm_memory}"
    )

    try:
        # 3. Stream inference request via OpenRouter
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:5000",
                "X-Title": "Eris Mainframe"
            },
            json={
                "model": "openrouter/free",
                "messages": [
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt}
                ]
            }
        )

        response_data = response.json()

        if 'choices' in response_data and len(response_data['choices']) > 0:
            ai_response = response_data['choices'][0]['message']['content']
            model_badge = "ERIS-FREE-MATRIX"

            # --- OPTION 1: BACKGROUND LONG-TERM MEMORY EXTRACTOR ---
            # If the user tells the AI a fact about themselves, extract it into the permanent vault
            if len(prompt) > 10:
                try:
                    memory_prompt = (
                        "Analyze this user statement. If it contains permanent personal facts, preferences, "
                        "project goals, or tech stack requirements about the user, extract it as a single concise sentence insight. "
                        "If it's just casual greeting or general talk, reply with 'IGNORE'.\n\n"
                        f"User Statement: \"{prompt}\""
                    )
                    mem_res = requests.post(
                        url="https://openrouter.ai/api/v1/chat/completions",
                        headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}",
                                 "Content-Type": "application/json"},
                        json={"model": "openrouter/free",
                              "messages": [{"role": "user", "content": memory_prompt}]}
                    ).json()

                    insight = mem_res['choices'][0]['message']['content'].strip(
                    )
                    if "IGNORE" not in insight and len(insight) > 5:
                        # Write the insight straight into eris_vault.db
                        vault_conn = sqlite3.connect("eris_vault.db")
                        v_cursor = vault_conn.cursor()
                        v_cursor.execute(
                            "INSERT INTO memory_vault (google_id, source_session_id, key_insight, content_vector_summary) VALUES (?, ?, ?, ?)",
                            (google_id, session_id, insight, prompt[:30])
                        )
                        vault_conn.commit()
                        vault_conn.close()
                        print(f"[Vault Updated Memory Core]: {insight}")
                except Exception as mem_err:
                    print(f"Memory vault archiving bypass: {str(mem_err)}")

        elif 'error' in response_data:
            ai_response = f"Mainframe API authorization fault: {response_data['error'].get('message', 'Unknown API Error')}"
            model_badge = "API-ERROR-LOG"
        else:
            ai_response = "Mainframe internal relay error. Received an unparseable response array."
            model_badge = "PAYLOAD-FAULT"

    except Exception as e:
        print(f"Upstream free generation inference fault: {str(e)}")
        ai_response = "Mainframe processing pipeline congestion. Live free AI channel failed to return text tokens."
        model_badge = "ERROR-FALLBACK"

    # Save generated AI answer back into tracking dataset
    cursor.execute(
        "INSERT INTO messages (session_id, role, content) VALUES (?, 'assistant', ?)", (session_id, ai_response))

    conn.commit()
    conn.close()

    return jsonify({
        "session_id": session_id,
        "response": ai_response,
        "model_used": model_badge
    })


if __name__ == "__main__":
    # Look for the cloud provider's port environment variable, default to 5000 locally
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
