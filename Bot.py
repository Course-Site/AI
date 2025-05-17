from flask import Flask, request, jsonify
from flask_cors import CORS
from gigachat import GigaChat
import psycopg2
import os
import uuid
import requests
from functools import wraps
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# Конфигурация
NESTJS_BACKEND_URL = os.getenv("NESTJS_BACKEND_URL")
JWT_SECRET = os.getenv("JWT_SECRET_KEY")
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "ai_chat"),
    "user": os.getenv("DB_USERNAME", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432")
}

# Инициализация GigaChat
giga = GigaChat(credentials=os.getenv("GIGACHAT_API_KEY"), verify_ssl_certs=False)

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

def init_db():
    """Инициализация структуры БД с привязкой к user_id"""
    commands = [
        """
        CREATE TABLE IF NOT EXISTS ai_messages (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(36) NOT NULL,
            role VARCHAR(50) NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    ]
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            for cmd in commands:
                cur.execute(cmd)
        conn.commit()
    except Exception as e:
        print(f"Ошибка инициализации БД: {e}")
        raise
    finally:
        conn.close()

init_db()

def verify_jwt(token: str):
    try:
        response = requests.post(
            f"{NESTJS_BACKEND_URL}/api/v1/auth/verify",
            headers={"Authorization": f"Bearer {token}"},
            timeout=3
        )
        return response.json() if response.status_code in (200, 201) else None
    except Exception as e:
        print(f"Verification error: {str(e)}")
        return None

def jwt_required(f):
    """Декоратор для проверки JWT"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"error": "Требуется JWT токен"}), 401
            
        token = auth_header.split(" ")[1]
        user_data = verify_jwt(token)
        
        if not user_data:
            return jsonify({"error": "Неверный или просроченный токен"}), 401
            
        return f(user_data['userId'], *args, **kwargs)
    return decorated

@app.route('/ai/chat', methods=['POST'])
@jwt_required
def ai_chat(user_id):
    """Основной endpoint для чата с ИИ"""
    try:
        data = request.json
        message = data.get('message', '').strip()
        
        if not message:
            return jsonify({"error": "Сообщение не может быть пустым"}), 400
        
        # Получаем ответ от GigaChat
        response = giga.chat(message)
        ai_reply = response.choices[0].message.content
        
        # Сохраняем в БД
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO ai_messages 
                (user_id, role, content) 
                VALUES (%s, %s, %s), (%s, %s, %s)""",
                (user_id, 'user', message,
                 user_id, 'assistant', ai_reply)
            )
            conn.commit()
        
        return jsonify({
            "reply": ai_reply,
            "user_id": user_id
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if 'conn' in locals():
            conn.close()

@app.route('/ai/history', methods=['GET'])
@jwt_required
def ai_history(user_id):
    """Получение истории сообщений по user_id"""
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Получаем историю сообщений
            cur.execute("""
                SELECT role, content, created_at 
                FROM ai_messages 
                WHERE user_id = %s
                ORDER BY created_at
            """, (user_id,))
            
            messages = [{
                'role': row[0],
                'content': row[1],
                'timestamp': row[2].isoformat()
            } for row in cur.fetchall()]
        
        return jsonify({"messages": messages})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)