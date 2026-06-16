from datetime import datetime, timedelta
from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from config import get_settings

settings = get_settings()
bearer = HTTPBearer()

def hash_senha(senha: str) -> str:
    return bcrypt.hashpw(senha.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verificar_senha(senha: str, hash: str) -> bool:
    try:
        return bcrypt.checkpw(senha.encode('utf-8'), hash.encode('utf-8'))
    except Exception:
        return False

def criar_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def decodificar_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")

def get_usuario_atual(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    return decodificar_token(credentials.credentials)

def requer_perfil(*perfis):
    def verificar(usuario=Depends(get_usuario_atual)):
        if usuario.get("perfil") not in perfis:
            raise HTTPException(status_code=403, detail="Sem permissão")
        return usuario
    return verificar
