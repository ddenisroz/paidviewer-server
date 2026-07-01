from core.database import UserToken


def test_user_diagnostics_endpoint_is_read_only(admin_client, db_session, test_user):
    db_session.add(
        UserToken(
            user_id=test_user.id,
            platform="twitch",
            platform_user_id="diagnostics-user",
            access_token="token",
            refresh_token="refresh",
            auth_type="full",
            is_active=True,
        )
    )
    db_session.commit()

    response = admin_client.get("/api/database/users/diagnostics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["mode"] == "read_only"
    assert data["automatic_deletes"] is False
    assert data["users"]["total"] >= 1
    assert data["sessions"]["total"] >= 0
    assert data["dry_run_cleanup"]["would_delete_users"] == 0

    remaining = db_session.query(UserToken).filter(
        UserToken.user_id == test_user.id,
        UserToken.platform_user_id == "diagnostics-user",
    ).first()
    assert remaining is not None
