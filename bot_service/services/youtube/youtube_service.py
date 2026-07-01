# bot_service/services/youtube/youtube_service.py
# -*- coding: utf-8 -*-
import asyncio
import re
import aiohttp
import logging
from typing import Optional, Dict, Any

from core.retry_utils import retry_async

logger = logging.getLogger('bot_service')

class YouTubeService:
    """
    Service for working with the YouTube API.
    """

    def __init__(self):
        from core.config import settings
        self.api_key = settings.google_cloud_api_key or settings.youtube_api_key
        self.base_url = "https://www.googleapis.com/youtube/v3"

    async def get_video_info(self, video_url: str) -> Optional[Dict[str, Any]]:
        """Fetch YouTube video information."""
        try:
            video_id = self._extract_video_id(video_url)
            if not video_id:
                logger.error(f"Could not extract video ID from URL: {video_url}")
                return None

            if not self.api_key:
                logger.warning("YouTube API key not configured, using fallback method")
                return await self._get_video_info_fallback(video_id, video_url)

            # Request YouTube data with retry support.
            async def _do_request():
                timeout = aiohttp.ClientTimeout(total=30, connect=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    url = f"{self.base_url}/videos"
                    params = {
                        'part': 'snippet,contentDetails,statistics',
                        'id': video_id,
                        'key': self.api_key
                    }
                    async with session.get(url, params=params) as response:
                        status = response.status
                        if status == 200:
                            data = await response.json()
                        else:
                            data = await response.text()
                        return status, data

            response = await retry_async(
                _do_request,
                max_attempts=3,
                initial_delay=2.0,
                retry_on=(aiohttp.ClientError, aiohttp.ClientConnectorError)
            )

            if not response:
                logger.error(f"YouTube API request failed after retries for: {video_id}")
                return await self._get_video_info_fallback(video_id, video_url)

            status, data = response

            if status == 200:

                if not data.get('items'):
                    logger.error(f"Video not found: {video_id}")
                    return None

                video_data = data['items'][0]
                return self._parse_video_data(video_data, video_url)
            else:
                logger.error(f"YouTube API error: {status} - {data}")
                return await self._get_video_info_fallback(video_id, video_url)

        except Exception:
            logger.exception("Error getting video info")
            try:
                video_id = self._extract_video_id(video_url)
                if video_id:
                    return await self._get_video_info_fallback(video_id, video_url)
            except Exception:
                pass
            return None

    def _extract_video_id(self, url: str) -> Optional[str]:
        """Extract a video ID from a YouTube URL."""
        try:
            # Supported URL formats:
            # https://www.youtube.com/watch?v=VIDEO_ID
            # https://youtu.be/VIDEO_ID
            # https://www.youtube.com/embed/VIDEO_ID
            # https://www.youtube.com/v/VIDEO_ID

            patterns = [
                r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/)([^&\n?#]+)',
                r'youtube\.com/watch\?.*v=([^&\n?#]+)',
            ]

            for pattern in patterns:
                match = re.search(pattern, url)
                if match:
                    return match.group(1)

            return None

        except Exception:
            logger.exception("Error extracting video ID")
            return None

    async def _get_video_info_fallback(self, video_id: str, video_url: str) -> Dict[str, Any]:
        """Fallback video info retrieval when API calls fail."""
        try:
            # First fallback: read metadata via pytube.
            try:
                from pytube import YouTube

                def _read_pytube_info() -> Dict[str, Any]:
                    yt = YouTube(video_url)
                    return {
                        'title': yt.title or f"YouTube Video {video_id}",
                        'duration': self._format_duration_seconds(yt.length or 0),
                        'thumbnail_url': yt.thumbnail_url or f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg",
                        'channel_title': yt.author or "Unknown Channel",
                        'view_count': yt.views or 0,
                        'description': (yt.description or "")[:500],
                    }

                pytube_info = await asyncio.to_thread(_read_pytube_info)

                return {
                    'video_id': video_id,
                    'title': pytube_info['title'],
                    'duration': pytube_info['duration'],
                    'thumbnail_url': pytube_info['thumbnail_url'],
                    'channel_title': pytube_info['channel_title'],
                    'view_count': pytube_info['view_count'],
                    'like_count': 0,
                    'description': pytube_info['description'],
                    'url': video_url,
                    'is_fallback': True
                }
            except Exception as pytube_error:
                logger.warning(f"Pytube fallback failed: {pytube_error}")

                yt_dlp_info = await self._get_video_info_yt_dlp(video_url)
                if yt_dlp_info:
                    return yt_dlp_info

                # Last resort fallback if yt-dlp also fails.
                return {
                    'video_id': video_id,
                    'title': f"YouTube Video {video_id}",
                    'duration': "0:00",
                    'thumbnail_url': f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg",
                    'channel_title': "Unknown Channel",
                    'view_count': 0,
                    'like_count': 0,
                    'description': "",
                    'url': video_url,
                    'is_fallback': True
                }

        except Exception:
            logger.exception("Error in fallback method")
            return None

    def _parse_video_data(self, video_data: Dict[str, Any], video_url: str) -> Dict[str, Any]:
        """Parse video data returned by the YouTube API."""
        try:
            snippet = video_data.get('snippet', {})
            content_details = video_data.get('contentDetails', {})
            statistics = video_data.get('statistics', {})

            # Parse the ISO 8601 duration field.
            duration_iso = content_details.get('duration', 'PT0S')
            duration_formatted = self._parse_duration(duration_iso)

            return {
                'video_id': video_data.get('id'),
                'title': snippet.get('title', 'Unknown Title'),
                'duration': duration_formatted,
                'thumbnail_url': snippet.get('thumbnails', {}).get('medium', {}).get('url', ''),
                'channel_title': snippet.get('channelTitle', 'Unknown Channel'),
                'view_count': int(statistics.get('viewCount', 0)),
                'like_count': int(statistics.get('likeCount', 0)),
                'description': snippet.get('description', ''),
                'published_at': snippet.get('publishedAt'),
                'url': video_url,
                'is_fallback': False
            }

        except Exception:
            logger.exception("Error parsing video data")
            return self._get_video_info_fallback(video_data.get('id', ''), video_url)

    def _parse_duration(self, duration_iso: str) -> str:
        """Convert an ISO 8601 duration to a human-readable format."""
        try:
            # PT4M13S -> 4:13
            # PT1H30M -> 1:30:00

            import re

            # Strip the PT prefix.
            duration = duration_iso.replace('PT', '')

            # Extract hours, minutes, and seconds.
            hours_match = re.search(r'(\d+)H', duration)
            minutes_match = re.search(r'(\d+)M', duration)
            seconds_match = re.search(r'(\d+)S', duration)

            hours = int(hours_match.group(1)) if hours_match else 0
            minutes = int(minutes_match.group(1)) if minutes_match else 0
            seconds = int(seconds_match.group(1)) if seconds_match else 0

            if hours > 0:
                return f"{hours}:{minutes:02d}:{seconds:02d}"
            else:
                return f"{minutes}:{seconds:02d}"

        except Exception:
            logger.exception("Error parsing duration")
            return "Unknown"

    def _format_duration_seconds(self, duration: Optional[int]) -> str:
        """Format seconds to H:MM:SS or M:SS."""
        try:
            total_seconds = int(duration or 0)
            if total_seconds <= 0:
                return "0:00"
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            if hours > 0:
                return f"{hours}:{minutes:02d}:{seconds:02d}"
            return f"{minutes}:{seconds:02d}"
        except Exception:
            logger.exception("Error formatting duration")
            return "0:00"

    async def _get_video_info_yt_dlp(self, video_url: str) -> Optional[Dict[str, Any]]:
        """Fallback video info via yt-dlp without downloading."""
        try:
            import yt_dlp
        except Exception as import_error:
            logger.warning(f"yt-dlp not available: {import_error}")
            return None

        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'skip_download': True,
                'extract_flat': False
            }

            def _extract_info() -> dict:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(video_url, download=False)

            info = await asyncio.to_thread(_extract_info)

            if not info:
                return None
            video_id = info.get('id') or self._extract_video_id(video_url) or ''
            thumbnail = info.get('thumbnail') or f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg"
            return {
                'video_id': video_id,
                'title': info.get('title') or f"YouTube Video {video_id}",
                'duration': self._format_duration_seconds(info.get('duration')),
                'thumbnail_url': thumbnail,
                'channel_title': info.get('uploader') or "Unknown Channel",
                'view_count': info.get('view_count') or 0,
                'like_count': info.get('like_count') or 0,
                'description': (info.get('description') or "")[:500],
                'url': video_url,
                'is_fallback': True
            }
        except Exception:
            logger.exception("yt-dlp info fallback failed")
            return None

    async def _search_videos_yt_dlp(self, query: str, max_results: int = 5) -> list:
        """Fallback search via yt-dlp."""
        try:
            import yt_dlp
        except Exception as import_error:
            logger.warning(f"yt-dlp not available for search: {import_error}")
            return []

        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'default_search': f"ytsearch{max_results}",
                'extract_flat': True,
                'skip_download': True,
            }
            results = []

            def _extract_search() -> dict:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(query, download=False)

            info = await asyncio.to_thread(_extract_search)

            for entry in (info.get('entries') or [])[:max_results]:
                video_id = entry.get('id')
                if not video_id:
                    continue
                results.append({
                    'video_id': video_id,
                    'title': entry.get('title'),
                    'url': f"https://www.youtube.com/watch?v={video_id}",
                    'thumbnail_url': entry.get('thumbnail', f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg"),
                    'channel_title': entry.get('uploader', 'Unknown')
                })
            return results
        except Exception:
            logger.exception("yt-dlp search fallback failed")
            return []

    def is_valid_youtube_url(self, url: str) -> bool:
        """Check whether a YouTube URL is valid."""
        try:
            video_id = self._extract_video_id(url)
            return video_id is not None and len(video_id) == 11
        except Exception:
            return False

    def get_embed_url(self, video_id: str) -> str:
        """Build an embeddable YouTube URL."""
        return f"https://www.youtube.com/embed/{video_id}"

    async def search_videos(self, query: str, max_results: int = 5) -> list:
        """Search videos by free-text query."""
        try:
            if not self.api_key:
                logger.warning("YouTube API key not configured for search")
                return await self._search_videos_yt_dlp(query, max_results)

            url = f"{self.base_url}/search"
            params = {
                'part': 'snippet',
                'q': query,
                'type': 'video',
                'maxResults': max_results,
                'key': self.api_key
            }

            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = []

                        for item in data.get('items', []):
                            video_id = item['id']['videoId']
                            snippet = item['snippet']

                            results.append({
                                'video_id': video_id,
                                'title': snippet.get('title'),
                                'url': f"https://www.youtube.com/watch?v={video_id}",
                                'thumbnail_url': snippet.get('thumbnails', {}).get('medium', {}).get('url'),
                                'channel_title': snippet.get('channelTitle')
                            })

                        return results
                    else:
                        logger.error(f"YouTube search API error: {response.status}")
                        return await self._search_videos_yt_dlp(query, max_results)

        except Exception:
            logger.exception("Error searching videos")
            return await self._search_videos_yt_dlp(query, max_results)


