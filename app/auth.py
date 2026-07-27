"""
Authentification et autorisation.
JWT simple (email + mot de passe -> token), stocké en base (mot_de_passe_hash),
sans dépendance externe (pas de Keycloak pour l'instant — trop tôt pour cette
complexité tant que le frontend n'existe pas encore).

Utilisation dans un router :
    from ..auth import get_current_user, exiger_role
    @router.patch(...)
    def endpoint(..., user: models.Utilisateur = Depends(exiger_role("super_administrateur"))):
        ...
"""

import os
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from . import models
from .database import get_db

# À changer en production — ici lu depuis une variable d'environnement,
# avec une valeur de secours uniquement pour le développement local.
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-only-secret-a-changer-en-production")
ALGORITHM = "HS256"
DUREE_TOKEN_MINUTES = 60 * 8  # 8h, une journée de travail

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def hacher_mot_de_passe(mot_de_passe: str) -> str:
    return pwd_context.hash(mot_de_passe)


def verifier_mot_de_passe(mot_de_passe: str, hash_stocke: str) -> bool:
    return pwd_context.verify(mot_de_passe, hash_stocke)


def creer_token(utilisateur: models.Utilisateur) -> str:
    expiration = datetime.utcnow() + timedelta(minutes=DUREE_TOKEN_MINUTES)
    payload = {"sub": str(utilisateur.id), "role": utilisateur.role.value, "exp": expiration}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> models.Utilisateur:
    erreur_auth = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Identifiants invalides ou session expirée.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        raise erreur_auth

    utilisateur = db.get(models.Utilisateur, user_id)
    if utilisateur is None or not utilisateur.actif:
        raise erreur_auth
    # Dépose l'auteur dans la session : les listeners du journal d'audit le reliront au flush.
    db.info["auteur_id"] = utilisateur.id
    return utilisateur


def exiger_role(role_requis: str):
    """Dépendance FastAPI : n'autorise que les utilisateurs ayant ce rôle exact."""
    def verificateur(utilisateur: models.Utilisateur = Depends(get_current_user)) -> models.Utilisateur:
        if utilisateur.role.value != role_requis:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Action réservée au rôle '{role_requis}'.",
            )
        return utilisateur
    return verificateur
