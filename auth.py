import requests
from functools import wraps
from flask import request, jsonify
import os

NESTJS_URL = os.getenv("NESTJS_BACKEND_URL")

def nestjs_jwt_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"error": "Bearer token required"}), 401
            
        token = auth_header.split(" ")[1]
        
        try:
            # Запрос к Nest.js эндпоинту
            response = requests.post(
                f"{NESTJS_URL}/api/v1/auth/verify",
                headers={"Authorization": f"Bearer {token}"},
                timeout=3
            )
            
            if response.status_code != 200:
                return jsonify({"error": "Invalid token"}), 401
                
            data = response.json()
            return f(data['userId'], *args, **kwargs)
            
        except requests.exceptions.RequestException:
            return jsonify({"error": "Auth service unavailable"}), 503
            
    return decorated