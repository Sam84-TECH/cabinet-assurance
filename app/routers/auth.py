"""
Endpoints d'authentification : connexion et création de comptes.
Règle de bootstrap : si la table utilisateur est vide, la création est libre
(pour créer le tout premier compte Super Administrateur). Une fois qu'il existe
au moins un utilisateur, toute nouvelle création exige d'être connecté en tant
que Super Administrateur.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..auth import (
    hacher_mot_de_passe, verifier_mot_de_passe, creer_token, exiger_role, get_current_user,
)

router = APIRouter(prefix="/auth", tags=["Authentification"])


@router.get("/me", response_model=schemas.UtilisateurRead)
def profil_courant(user: models.Utilisateur = Depends(get_current_user)):
    """Profil de l'utilisateur connecté, déduit du jeton (id, nom, prénom, email, rôle, actif).
    Le hash du mot de passe n'est jamais exposé (absent de UtilisateurRead)."""
    return user


@router.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    utilisateur = db.query(models.Utilisateur).filter_by(email=form.username).first()
    if not utilisateur or not utilisateur.mot_de_passe_hash or not verifier_mot_de_passe(
        form.password, utilisateur.mot_de_passe_hash
    ):
        raise HTTPException(401, "Email ou mot de passe incorrect.")
    if not utilisateur.actif:
        raise HTTPException(403, "Ce compte est désactivé.")
    return {"access_token": creer_token(utilisateur), "token_type": "bearer"}


@router.post("/utilisateurs", response_model=schemas.UtilisateurRead)
def creer_utilisateur(payload: schemas.UtilisateurCreate, db: Session = Depends(get_db)):
    premier_compte = db.query(models.Utilisateur).count() == 0
    if not premier_compte:
        # À partir du 2e compte, on exige d'être connecté en Super Administrateur.
        # (Dépendance appliquée manuellement ici plutôt qu'en paramètre de route,
        # pour permettre le cas particulier du tout premier compte sans jeton.)
        raise HTTPException(
            403,
            "Un compte existe déjà : la création doit passer par un Super Administrateur connecté "
            "(endpoint /auth/utilisateurs/admin).",
        )

    data = payload.model_dump(exclude={"mot_de_passe"})
    data["mot_de_passe_hash"] = hacher_mot_de_passe(payload.mot_de_passe)
    data["role"] = models.RoleUtilisateur.super_administrateur  # le tout premier compte est admin
    from .. import crud
    return crud.create(db, models.Utilisateur, data)


@router.post("/utilisateurs/admin", response_model=schemas.UtilisateurRead)
def creer_utilisateur_par_admin(payload: schemas.UtilisateurCreate, db: Session = Depends(get_db),
                                 _admin: models.Utilisateur = Depends(exiger_role("super_administrateur"))):
    data = payload.model_dump(exclude={"mot_de_passe"})
    data["mot_de_passe_hash"] = hacher_mot_de_passe(payload.mot_de_passe)
    from .. import crud
    return crud.create(db, models.Utilisateur, data)
