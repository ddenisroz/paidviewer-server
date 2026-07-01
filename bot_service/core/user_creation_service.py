#!/usr/bin/env python3
"""
Centralized user-creation service.
Prevents duplicates and race conditions.
"""
import logging
from sqlalchemy.orm import Session
from core.database import User, UserToken
from core.datetime_utils import utcnow_naive
from core.token_encryption import encrypt_token
logger = logging.getLogger(__name__)

class UserCreationService:
    """Centralized service for creating users."""

    @staticmethod
    async def find_or_create_user(db: Session, platform: str, platform_user_id: str, username: str=None, avatar_url: str=None, access_token: str=None, refresh_token: str=None, expires_at=None, scopes: list=None, current_user_id: int=None, is_admin: bool=False) -> User:
        """
        Find an existing user or create a new one.
        Prevent duplicates and race conditions.
        """
        logger.info(f'[DEBUG] [USER_CREATION] Looking for user: {platform}:{platform_user_id}')
        if username:
            from sqlalchemy import func
            if platform == 'twitch':
                existing_user = db.query(User).filter(func.lower(User.twitch_username) == username.lower()).first()
            elif platform == 'vk':
                existing_user = db.query(User).filter(func.lower(User.vk_username) == username.lower()).first()
            else:
                existing_user = None
            if existing_user:
                logger.info(f"[OK] [USER_CREATION] Found existing user by username: {platform}='{username}' (ID: {existing_user.id})")
                if platform == 'twitch' and (not existing_user.twitch_username):
                    existing_user.twitch_username = username
                    db.commit()
                    logger.info(f'[REFRESH] [USER_CREATION] Set twitch_username to {username}')
                elif platform == 'vk' and (not existing_user.vk_username):
                    existing_user.vk_username = username
                    db.commit()
                    logger.info(f'[REFRESH] [USER_CREATION] Set vk_username to {username}')
                if access_token:
                    existing_token = db.query(UserToken).filter(UserToken.platform == platform, UserToken.platform_user_id == platform_user_id).first()
                    if existing_token:
                        logger.info(f'[REFRESH] [USER_CREATION] Updating token for existing user {existing_user.id}')
                        existing_token.user_id = existing_user.id
                        existing_token.access_token = encrypt_token(access_token)
                        existing_token.updated_at = utcnow_naive()
                        if refresh_token:
                            existing_token.refresh_token = encrypt_token(refresh_token)
                        if expires_at:
                            existing_token.expires_at = expires_at
                        if scopes:
                            existing_token.scopes = scopes
                        if avatar_url:
                            existing_token.avatar_url = avatar_url
                        db.commit()
                        logger.info(f'[OK] [USER_CREATION] Updated token for existing user {existing_user.id}')
                    else:
                        logger.info(f'[REFRESH] [USER_CREATION] Creating token for existing user {existing_user.id}')
                        new_token = UserToken(user_id=existing_user.id, platform=platform, platform_user_id=platform_user_id, access_token=encrypt_token(access_token), refresh_token=encrypt_token(refresh_token) if refresh_token else None, expires_at=expires_at, scopes=scopes, avatar_url=avatar_url)
                        db.add(new_token)
                        db.commit()
                        logger.info(f'[OK] [USER_CREATION] Created token for existing user {existing_user.id}')
                return existing_user
        existing_token = db.query(UserToken).filter(UserToken.platform == platform, UserToken.platform_user_id == platform_user_id).first()
        if existing_token:
            logger.info(f'[OK] [USER_CREATION] Found existing token for {platform}:{platform_user_id}')
            user = db.query(User).filter(User.id == existing_token.user_id).first()
            if user:
                if username and platform == 'twitch' and (not user.twitch_username):
                    user.twitch_username = username
                    db.commit()
                    logger.info(f'[REFRESH] [USER_CREATION] Updated twitch_username to {username}')
                elif username and platform == 'vk' and (not user.vk_username):
                    user.vk_username = username
                    db.commit()
                    logger.info(f'[REFRESH] [USER_CREATION] Updated vk_username to {username}')
                if access_token:
                    logger.info(f'[REFRESH] [USER_CREATION] Updating token for {platform}:{platform_user_id}')
                    existing_token.access_token = encrypt_token(access_token)
                    existing_token.updated_at = utcnow_naive()
                    if refresh_token:
                        existing_token.refresh_token = encrypt_token(refresh_token)
                    if expires_at:
                        existing_token.expires_at = expires_at
                    if scopes:
                        existing_token.scopes = scopes
                    if avatar_url:
                        existing_token.avatar_url = avatar_url
                    db.commit()
                    logger.info(f'[OK] [USER_CREATION] Updated token for {platform}:{platform_user_id}')
                return user
            else:
                logger.warning(f'[WARN] [USER_CREATION] Token exists but user {existing_token.user_id} not found')
                db.delete(existing_token)
                db.commit()
        if current_user_id:
            logger.info(f'[LINK] [USER_CREATION] Linking {platform} to existing user {current_user_id}')
            user = db.query(User).filter(User.id == current_user_id).first()
            if user:
                if username and platform == 'twitch' and (not user.twitch_username):
                    user.twitch_username = username
                    db.commit()
                    logger.info(f'[REFRESH] [USER_CREATION] Set twitch_username to {username}')
                elif username and platform == 'vk' and (not user.vk_username):
                    user.vk_username = username
                    db.commit()
                    logger.info(f'[REFRESH] [USER_CREATION] Set vk_username to {username}')
                return user
            else:
                logger.warning(f'[WARN] [USER_CREATION] Current user {current_user_id} not found')
        logger.info(f'[NEW] [USER_CREATION] Creating new user for {platform}:{platform_user_id}')
        try:
            role = 'admin' if is_admin else 'user'
            new_user = User(role=role)
            if username and platform == 'twitch':
                new_user.twitch_username = username
            elif username and platform == 'vk':
                new_user.vk_username = username
            db.add(new_user)
            db.commit()
            db.refresh(new_user)
            logger.info(f'[OK] [USER_CREATION] Created new user ID: {new_user.id}, role: {role}')
            if access_token:
                user_token = UserToken(user_id=new_user.id, platform=platform, platform_user_id=platform_user_id, access_token=encrypt_token(access_token), refresh_token=encrypt_token(refresh_token) if refresh_token else None, expires_at=expires_at, scopes=scopes, avatar_url=avatar_url)
                db.add(user_token)
                db.commit()
                logger.info(f'[OK] [USER_CREATION] Created token for user {new_user.id}')
            return new_user
        except Exception as e:
            logger.error(f'[ERROR] [USER_CREATION] Failed to create user: {e}')
            db.rollback()
            raise
user_creation_service = UserCreationService()
