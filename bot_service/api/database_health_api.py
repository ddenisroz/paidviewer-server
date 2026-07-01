# bot_service/api/database_health_api.py
"""
Database Health Monitoring API

Provides endpoints for monitoring database connection pool,
query performance, and overall database health.
"""
import logging
from core.datetime_utils import utcnow_naive

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.database import get_db, engine
from auth.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/database", tags=["database-health"])


@router.get("/pool-status")
async def get_pool_status(current_user: dict = Depends(get_current_user)):
    """
    Get database connection pool status.
    
    Returns:
        - size: Current pool size
        - checked_in: Available connections
        - checked_out: Active connections
        - overflow: Overflow connections
        - total: Total connections
        - utilization: Pool utilization percentage
    """
    if not (current_user.get("role") == "admin" or current_user.get("is_admin")):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        pool = engine.pool
        pool_class = pool.__class__.__name__
        
        # StaticPool is used in test mode and does not expose pool metrics.
        if pool_class == "StaticPool":
            return {
                "status": "healthy",
                "message": "Using StaticPool (testing mode)",
                "pool_size": 1,
                "pool_class": pool_class,
                "note": "StaticPool does not support connection pooling metrics",
                "timestamp": utcnow_naive().isoformat()
            }
        
        # For real connection pools (QueuePool, etc.)
        size = pool.size()
        checked_in = pool.checkedin()
        checked_out = pool.checkedout()
        overflow = pool.overflow()
        total = size + overflow
        
        # Calculate utilization
        utilization = (checked_out / total * 100) if total > 0 else 0
        
        # Determine health status
        if utilization > 90:
            status = "critical"
            message = "Pool utilization is very high"
        elif utilization > 75:
            status = "warning"
            message = "Pool utilization is high"
        else:
            status = "healthy"
            message = "Pool is operating normally"
        
        return {
            "status": status,
            "message": message,
            "pool_size": size,
            "pool_class": pool_class,
            "checked_in": checked_in,
            "checked_out": checked_out,
            "overflow": overflow,
            "total": total,
            "utilization_percent": round(utilization, 2),
            "timestamp": utcnow_naive().isoformat()
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting pool status")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/health")
async def database_health_check(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Comprehensive database health check.
    
    Checks:
        - Database connectivity
        - Query response time
        - Connection pool status
        - Active connections
    """
    if not (current_user.get("role") == "admin" or current_user.get("is_admin")):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    health_data = {
        "timestamp": utcnow_naive().isoformat(),
        "checks": {}
    }
    
    # 1. Connectivity check
    try:
        start_time = utcnow_naive()
        db.execute(text("SELECT 1"))
        response_time_ms = (utcnow_naive() - start_time).total_seconds() * 1000
        
        health_data["checks"]["connectivity"] = {
            "status": "healthy",
            "response_time_ms": round(response_time_ms, 2)
        }
    except Exception:
        health_data["checks"]["connectivity"] = {
            "status": "unhealthy",
            "error": "Internal server error"
        }
    
    # 2. Pool status
    try:
        pool = engine.pool
        pool_class = pool.__class__.__name__
        
        # StaticPool is used in test mode and does not expose pool metrics.
        if pool_class == "StaticPool":
            health_data["checks"]["connection_pool"] = {
                "status": "healthy",
                "pool_class": pool_class,
                "note": "StaticPool (testing mode) - no pooling metrics available"
            }
        else:
            checked_out = pool.checkedout()
            total = pool.size() + pool.overflow()
            utilization = (checked_out / total * 100) if total > 0 else 0
            
            pool_status = "healthy"
            if utilization > 90:
                pool_status = "critical"
            elif utilization > 75:
                pool_status = "warning"
            
            health_data["checks"]["connection_pool"] = {
                "status": pool_status,
                "pool_class": pool_class,
                "utilization_percent": round(utilization, 2),
                "active_connections": checked_out,
                "total_connections": total
            }
    except Exception:
        health_data["checks"]["connection_pool"] = {
            "status": "error",
            "error": "Internal server error"
        }
    
    # 3. Active queries check (PostgreSQL specific)
    try:
        result = db.execute(text("""
            SELECT COUNT(*) as active_queries
            FROM pg_stat_activity
            WHERE state = 'active'
            AND query NOT LIKE '%pg_stat_activity%'
        """))
        active_queries = result.scalar()
        
        health_data["checks"]["active_queries"] = {
            "status": "healthy",
            "count": active_queries
        }
    except Exception:
        # Not critical if this fails (might not be PostgreSQL)
        health_data["checks"]["active_queries"] = {
            "status": "unavailable",
            "error": "Internal server error"
        }
    
    # Overall status
    statuses = [check["status"] for check in health_data["checks"].values()]
    if "unhealthy" in statuses or "critical" in statuses:
        health_data["overall_status"] = "unhealthy"
    elif "warning" in statuses:
        health_data["overall_status"] = "warning"
    else:
        health_data["overall_status"] = "healthy"
    
    return health_data


@router.get("/slow-queries")
async def get_slow_queries(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(default=10, ge=1, le=100)
):
    """
    Get slow running queries (PostgreSQL specific).
    
    Helps identify N+1 query problems and performance issues.
    """
    if not (current_user.get("role") == "admin" or current_user.get("is_admin")):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        result = db.execute(text("""
            SELECT
                pid,
                usename,
                application_name,
                client_addr,
                state,
                query,
                query_start,
                EXTRACT(EPOCH FROM (NOW() - query_start)) as duration_seconds
            FROM pg_stat_activity
            WHERE state = 'active'
            AND query NOT LIKE '%pg_stat_activity%'
            ORDER BY query_start ASC
            LIMIT :limit
        """), {"limit": limit})
        
        queries = []
        for row in result:
            queries.append({
                "pid": row.pid,
                "user": row.usename,
                "application": row.application_name,
                "client": str(row.client_addr) if row.client_addr else None,
                "state": row.state,
                "query": row.query[:500],  # Truncate long queries
                "started_at": row.query_start.isoformat() if row.query_start else None,
                "duration_seconds": round(row.duration_seconds, 2) if row.duration_seconds else 0
            })
        
        return {
            "slow_queries": queries,
            "count": len(queries),
            "timestamp": utcnow_naive().isoformat()
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting slow queries")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/table-stats")
async def get_table_statistics(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get table statistics including row counts and sizes.
    
    Useful for monitoring database growth and identifying large tables.
    """
    if not (current_user.get("role") == "admin" or current_user.get("is_admin")):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        result = db.execute(text("""
            SELECT
                schemaname,
                tablename,
                pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size,
                pg_total_relation_size(schemaname||'.'||tablename) AS size_bytes,
                n_live_tup AS row_count
            FROM pg_stat_user_tables
            ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
            LIMIT 20
        """))
        
        tables = []
        for row in result:
            tables.append({
                "schema": row.schemaname,
                "table": row.tablename,
                "size": row.size,
                "size_bytes": row.size_bytes,
                "row_count": row.row_count
            })
        
        return {
            "tables": tables,
            "timestamp": utcnow_naive().isoformat()
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting table stats")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/index-usage")
async def get_index_usage(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get index usage statistics.
    
    Helps identify unused indexes (waste of space) and missing indexes.
    """
    if not (current_user.get("role") == "admin" or current_user.get("is_admin")):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        result = db.execute(text("""
            SELECT
                schemaname,
                tablename,
                indexname,
                idx_scan,
                idx_tup_read,
                idx_tup_fetch,
                pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
            FROM pg_stat_user_indexes
            ORDER BY idx_scan ASC, pg_relation_size(indexrelid) DESC
            LIMIT 20
        """))
        
        indexes = []
        for row in result:
            # Determine if index is unused
            is_unused = row.idx_scan == 0
            
            indexes.append({
                "schema": row.schemaname,
                "table": row.tablename,
                "index": row.indexname,
                "scans": row.idx_scan,
                "tuples_read": row.idx_tup_read,
                "tuples_fetched": row.idx_tup_fetch,
                "size": row.index_size,
                "is_unused": is_unused,
                "warning": "Consider removing this index" if is_unused else None
            })
        
        return {
            "indexes": indexes,
            "unused_count": sum(1 for idx in indexes if idx["is_unused"]),
            "timestamp": utcnow_naive().isoformat()
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting index usage")
        raise HTTPException(status_code=500, detail="Internal server error")
