# import asyncio
# import json
# import logging
# from unittest.mock import AsyncMock
# from unittest.mock import patch

# import pytest

# from backend.sse_event_streams import SSE_KEEPALIVE_TIMEOUT
# from backend.sse_event_streams import admin_updates_generator
# from backend.sse_event_streams import make_sse_update_message
# from backend.sse_event_streams import updates_generator
# from backend.user_interface import UserInterface
# from backend.model import Shot

# logger = logging.getLogger(__name__)


# @pytest.fixture
# def mock_user_interface():
#     with patch("backend.sse_event_streams.UserInterface") as MockUserInterface:
#         yield MockUserInterface


# @pytest.fixture
# def mock_admin_interface():
#     with patch("backend.sse_event_streams.AdminInterface") as MockAdminInterface:
#         yield MockAdminInterface


# @pytest.mark.asyncio
# async def test_ticker_announces_kill(
#     db_session,
#     api_client,
#     admin_api_client,
#     api_user_id,
#     team_factory,
#     test_image_string,
# ):
#     # Put a user in a team and have them take a shot
#     UserInterface(api_user_id).join_team(team_factory())
#     UserInterface(api_user_id).award_ammo(1)
#     UserInterface(api_user_id).submit_shot(test_image_string)
#     shot_a = db_session.query(Shot.id).order_by(Shot.id.desc()).first()[0]

#     # Subscribe to the ticker update queue for this user
#     ticker_generator = UserInterface(api_user_id).generate_ticker_updates()

#     # Read one message to make sure the event is subscribed to
#     m = await anext(ticker_generator)

#     # Let's say the user shot themselves:
#     response = await admin_api_client.post(
#         f"/api/admin_shot_hit_user?shot_id={shot_a}&target_user_id={api_user_id}"
#     )
#     assert response.is_success

#     # Check that the ticker announces the kill
