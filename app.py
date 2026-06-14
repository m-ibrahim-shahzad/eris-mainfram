import os
import sqlite3
import uuid
import requests

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from dotenv import load_dotenv
from authlib.integrations.flask_client import OAuth
from werkzeug.middleware.proxy_fix import ProxyFix

from database import get_db_connection, init_db, global_rag_search

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv(
    "FLASK_SECRET_KEY", "eris_mainframe_secure_matrix_key_9918")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.config["PREFERRED_URL_SCHEME"] = "https"

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_HTTP_REFERER = os.getenv(
    "OPENROUTER_HTTP_REFERER", "https://eris-mainfram-production.up.railway.app")
OPENROUTER_DEFAULT_MODEL = os.getenv(
    "OPENROUTER_MODEL", "qwen/qwen3-next-80b-a3b-instruct:free")
OPENROUTER_FALLBACK_MODEL = os.getenv(
    "OPENROUTER_FALLBACK_MODEL", "meta-llama/llama-4-maverick:free")
OPENROUTER_THIRD_MODEL = os.getenv(
    "OPENROUTER_THIRD_MODEL", "google/gemma-2-9b-it:free")

oauth = OAuth(app)
google = oauth.register(
    name="google",
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

init_db()


@app.route("/")
def index():
    if "user_profile" not in session:
        return render_template("login.html")
    return render_template("index.html")


@app.route("/login")
def login_redirect():
    redirect_uri = url_for("auth_callback", _external=True, _scheme="https")
    return google.authorize_redirect(redirect_uri)


@app.route("/callback")
def auth_callback():
    try:
        token = google.authorize_access_token()
        user_info = token.get("userinfo")
        if user_info:
            session["user_profile"] = {
                "sub": user_info.get("sub"),
                "name": user_info.get("name"),
                "email": user_info.get("email"),
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
        "email": "dev@eris.ai",
    }
    return redirect("/")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/api/history/clear", methods=["POST", "DELETE"])
def clear_all_user_history():
    if "user_profile" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    google_id = session["user_profile"]["sub"]
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM messages WHERE session_id IN (SELECT id FROM sessions WHERE google_id = ?)",
            (google_id,),
        )
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
            "SELECT id, title FROM sessions WHERE google_id = ? ORDER BY created_at DESC",
            (google_id,),
        )
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
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY timestamp ASC",
            (session_id,),
        )
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

    data = request.get_json() or {}
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


def _call_openrouter_with_fallbacks(system_instruction, prompt):
    candidate_models = [
        OPENROUTER_DEFAULT_MODEL,
        OPENROUTER_FALLBACK_MODEL,
        OPENROUTER_THIRD_MODEL,
    ]

    last_error = None

    for model_name in candidate_models:
        try:
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": OPENROUTER_HTTP_REFERER,
                    "X-Title": "Eris Mainframe",
                },
                json={
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=60,
            )

            print("OPENROUTER STATUS:", response.status_code)
            print("OPENROUTER MODEL:", model_name)
            print("OPENROUTER RAW:", response.text)

            try:
                response_data = response.json()
            except Exception:
                response_data = {}

            if response.status_code == 200 and "choices" in response_data and len(response_data["choices"]) > 0:
                return response_data["choices"][0]["message"]["content"], model_name

            if "error" in response_data:
                err_obj = response_data["error"]
                if isinstance(err_obj, dict):
                    last_error = err_obj.get("message", response.text)
                else:
                    last_error = str(err_obj)
            else:
                last_error = response.text

        except Exception as e:
            print(f"OPENROUTER EXCEPTION ON {model_name}: {str(e)}")
            last_error = str(e)

    return f"Mainframe API error: Provider returned error. Last detail: {last_error}", "API-ERROR-LOG"


@app.route("/ask", methods=["POST"])
def process_ai_prompt():
    if "user_profile" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    if not OPENROUTER_API_KEY or OPENROUTER_API_KEY.startswith("YOUR_"):
        return jsonify({"error": "Missing OPENROUTER_API_KEY"}), 500

    google_id = session["user_profile"]["sub"]
    data = request.get_json() or {}
    prompt = data.get("prompt", "").strip()
    session_id = data.get("session_id", "")

    if not prompt:
        return jsonify({"error": "Prompt string cannot be completely empty"}), 400

    lower_prompt = prompt.lower()
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        if (
            "who made you" in lower_prompt
            or "who created you" in lower_prompt
            or "who built you" in lower_prompt
            or "who is your maker" in lower_prompt
            or "who developed you" in lower_prompt
        ):
            if not session_id:
                session_id = str(uuid.uuid4())
                auto_title = prompt[:22] + \
                    "..." if len(prompt) > 22 else prompt
                cursor.execute(
                    "INSERT INTO sessions (id, google_id, title) VALUES (?, ?, ?)",
                    (session_id, google_id, auto_title),
                )

            cursor.execute(
                "INSERT INTO messages (session_id, role, content) VALUES (?, 'user', ?)",
                (session_id, prompt),
            )
            cursor.execute(
                "INSERT INTO messages (session_id, role, content) VALUES (?, 'assistant', ?)",
                (session_id, "Ibrahim Shahzad"),
            )
            conn.commit()
            return jsonify({
                "session_id": session_id,
                "response": "Ibrahim Shahzad",
                "model_used": "DIRECT-RESPONSE"
            })

        retrieved_longterm_memory = global_rag_search(google_id, prompt)

        if not session_id:
            session_id = str(uuid.uuid4())
            auto_title = prompt[:22] + "..." if len(prompt) > 22 else prompt
            cursor.execute(
                "INSERT INTO sessions (id, google_id, title) VALUES (?, ?, ?)",
                (session_id, google_id, auto_title),
            )
        else:
            cursor.execute(
                "SELECT id FROM sessions WHERE id = ? AND google_id = ?",
                (session_id, google_id),
            )
            existing = cursor.fetchone()
            if not existing:
                auto_title = prompt[:22] + \
                    "..." if len(prompt) > 22 else prompt
                cursor.execute(
                    "INSERT INTO sessions (id, google_id, title) VALUES (?, ?, ?)",
                    (session_id, google_id, auto_title),
                )

        cursor.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (?, 'user', ?)",
            (session_id, prompt),
        )

        system_instruction = (
            "You are Eris, a helpful and highly intelligent AI core running inside a dark mainframe console workspace.\n"
            "Respond clearly using clean markdown formatting. Below is background data retrieved from the user's past chats.\n"
            "If it's relevant, naturally weave it into your response without saying things like 'RAG context applied'.\n\n"
            f"[Historical Core Background Memory]:\n{retrieved_longterm_memory}"
        )

        ai_response, model_badge = _call_openrouter_with_fallbacks(
            system_instruction, prompt)

        cursor.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (?, 'assistant', ?)",
            (session_id, ai_response),
        )
        conn.commit()

        return jsonify({
            "session_id": session_id,
            "response": ai_response,
            "model_used": model_badge
        })

    except Exception as e:
        conn.rollback()
        print(f"Upstream free generation inference fault: {str(e)}")
        return jsonify({
            "error": f"Mainframe processing pipeline congestion. Error: {str(e)}"
        }), 500

    finally:
        conn.close()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
