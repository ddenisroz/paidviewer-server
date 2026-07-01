"""
OpenAPI Configuration for API Documentation and Type Generation

This module configures FastAPI's OpenAPI schema generation with:
- Detailed API documentation
- Type-safe schema for frontend TypeScript generation
- Proper error response schemas
- Authentication documentation
"""
from fastapi.openapi.utils import get_openapi
from fastapi import FastAPI


def custom_openapi(app: FastAPI):
    """
    Generate custom OpenAPI schema with enhanced documentation
    
    Usage:
        app.openapi = lambda: custom_openapi(app)
    """
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="TTS Bot API",
        version="0.03",
        description="""
# TTS Bot API Documentation

Production-ready text-to-speech bot for streamers on Twitch and VK Live platforms.

## Features

- **Multi-Platform Support**: Twitch and VK Live integration
- **TTS Engines**: Google Cloud TTS, F5-TTS
- **YouTube Integration**: Queue management and player
- **Channel Points System**: Twitch and VK Live rewards
- **Drops System**: Lootbox mechanics with streak tracking
- **DonationAlerts**: Automatic integration
- **Custom Commands**: Global, override, and custom commands
- **Permission System**: Role-based access control
- **Admin Panel**: User and voice management
- **OBS Widgets**: Chat, TTS, YouTube, and Drops overlays

## Authentication

Most endpoints require authentication via session cookies.

1. Login via OAuth (Twitch or VK Live)
2. Receive session cookie
3. Include cookie in subsequent requests

## Rate Limiting

- Default: 60 requests/minute per user
- Login: 5 requests/15 minutes per IP
- TTS: 30 requests/minute per user
- Admin: 100 requests/minute per admin

## Error Responses

All errors follow this format:

```json
{
  "error_code": "VALIDATION_ERROR",
  "message": "Human-readable error message",
  "details": {
    "field": "Additional error details"
  },
  "timestamp": "2025-12-18T12:00:00Z"
}
```

### Error Codes

- `AUTHENTICATION_ERROR` - Invalid or missing authentication
- `AUTHORIZATION_ERROR` - Insufficient permissions
- `VALIDATION_ERROR` - Invalid input data
- `NOT_FOUND` - Resource not found
- `RATE_LIMIT_EXCEEDED` - Too many requests
- `PLATFORM_ERROR` - Platform API error
- `TTS_ERROR` - TTS service error
- `DATABASE_ERROR` - Database operation failed
- `INTERNAL_ERROR` - Unexpected server error

## Pagination

List endpoints support pagination:

```
GET /api/endpoint?page=1&per_page=20
```

Response includes:
```json
{
  "items": [...],
  "total": 100,
  "page": 1,
  "per_page": 20,
  "pages": 5
}
```
        """,
        routes=app.routes,
        tags=[
            {
                "name": "auth",
                "description": "Authentication and authorization endpoints"
            },
            {
                "name": "tts",
                "description": "Text-to-speech functionality"
            },
            {
                "name": "youtube",
                "description": "YouTube queue management"
            },
            {
                "name": "drops",
                "description": "Drops/lootbox system"
            },
            {
                "name": "points",
                "description": "Channel points and rewards"
            },
            {
                "name": "commands",
                "description": "Bot commands management"
            },
            {
                "name": "stream",
                "description": "Stream information and management"
            },
            {
                "name": "admin",
                "description": "Admin-only endpoints (requires admin role)"
            },
            {
                "name": "websocket",
                "description": "WebSocket connections for real-time updates"
            },
            {
                "name": "widgets",
                "description": "OBS widget endpoints"
            }
        ]
    )
    
    # Add security schemes
    openapi_schema["components"]["securitySchemes"] = {
        "SessionCookie": {
            "type": "apiKey",
            "in": "cookie",
            "name": "session_id",
            "description": "Session cookie obtained after OAuth login"
        }
    }
    
    # Add common response schemas
    openapi_schema["components"]["schemas"]["ErrorResponse"] = {
        "type": "object",
        "properties": {
            "error_code": {
                "type": "string",
                "enum": [
                    "INTERNAL_ERROR",
                    "AUTHENTICATION_ERROR",
                    "AUTHORIZATION_ERROR",
                    "TOKEN_EXPIRED",
                    "INVALID_TOKEN",
                    "SESSION_EXPIRED",
                    "NOT_FOUND",
                    "ALREADY_EXISTS",
                    "VALIDATION_ERROR",
                    "INVALID_INPUT",
                    "PLATFORM_ERROR",
                    "PLATFORM_CONNECTION_ERROR",
                    "PLATFORM_API_ERROR",
                    "BOT_ERROR",
                    "BOT_NOT_CONNECTED",
                    "BOT_ALREADY_CONNECTED",
                    "TTS_ERROR",
                    "TTS_SERVICE_UNAVAILABLE",
                    "TTS_VOICE_NOT_FOUND",
                    "DATABASE_ERROR",
                    "DATABASE_CONNECTION_ERROR",
                    "RATE_LIMIT_EXCEEDED",
                    "EXTERNAL_SERVICE_ERROR"
                ]
            },
            "message": {
                "type": "string",
                "description": "Human-readable error message"
            },
            "details": {
                "type": "object",
                "description": "Additional error details"
            },
            "timestamp": {
                "type": "string",
                "format": "date-time"
            }
        },
        "required": ["error_code", "message"]
    }
    
    openapi_schema["components"]["schemas"]["PaginatedResponse"] = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {}
            },
            "total": {
                "type": "integer",
                "description": "Total number of items"
            },
            "page": {
                "type": "integer",
                "description": "Current page number"
            },
            "per_page": {
                "type": "integer",
                "description": "Items per page"
            },
            "pages": {
                "type": "integer",
                "description": "Total number of pages"
            }
        },
        "required": ["items", "total", "page", "per_page", "pages"]
    }
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema


def setup_openapi(app: FastAPI):
    """
    Setup OpenAPI documentation for the FastAPI app
    
    Usage:
        from core.openapi_config import setup_openapi
        setup_openapi(app)
    """
    app.openapi = lambda: custom_openapi(app)
