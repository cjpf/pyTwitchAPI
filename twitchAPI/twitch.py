#  Copyright (c) 2020. Lena "Teekeks" During <info@teawork.de>

from .webhook import TwitchWebHook
import requests
from typing import Union, List, Optional
from .helper import build_url, TWITCH_API_BASE_URL, TWITCH_AUTH_BASE_URL, make_fields_datetime, build_scope, \
    fields_to_enum
from datetime import datetime
from .types import AnalyticsReportType, AuthScope, AuthType, UnauthorizedException, MissingScopeException, \
    TimePeriod, CodeStatus, ModerationEventType
from dateutil import parser as du_parser


class Twitch:
    app_id: Union[str, None] = None
    app_secret: Union[str, None] = None
    __app_auth_token: Union[str, None] = None
    __app_auth_scope: List[AuthScope] = []
    __has_app_auth: bool = False

    __user_auth_token: Union[str, None] = None
    __user_auth_scope: List[AuthScope] = []
    __has_user_auth: bool = False

    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret

    def __generate_header(self, auth_type: 'AuthType', required_scope: List[AuthScope]) -> dict:
        header = {"Client-ID": self.app_id}
        if auth_type == AuthType.APP:
            if not self.__has_app_auth:
                raise UnauthorizedException('Require app authentication!')
            for s in required_scope:
                if s not in self.__app_auth_scope:
                    raise MissingScopeException('Require app auth scope ' + s.name)
            header['Authorization'] = f'Bearer {self.__app_auth_token}'
        elif auth_type == AuthType.USER:
            if not self.__has_user_auth:
                raise UnauthorizedException('require user authentication!')
            for s in required_scope:
                if s not in self.__user_auth_scope:
                    raise MissingScopeException('Require user auth scope ' + s.name)
            header['Authorization'] = f'Bearer {self.__user_auth_token}'
        elif self.__has_user_auth or self.__has_app_auth:
            # if no required, set one anyway to get better rate limits if possible
            header['Authorization'] = \
                f'Bearer {self.__user_auth_token if self.__has_user_auth else self.__app_auth_token}'
        return header

    def __api_post_request(self,
                           url: str,
                           auth_type: 'AuthType',
                           required_scope: List[AuthScope],
                           data: Union[dict, None] = None):
        """Make POST request with Client-ID authorization"""
        headers = self.__generate_header(auth_type, required_scope)
        if data is None:
            return requests.post(url, headers=headers)
        else:
            return requests.post(url, headers=headers, json=data)

    def __api_put_request(self,
                          url: str,
                          auth_type: 'AuthType',
                          required_scope: List[AuthScope],
                          data: Union[dict, None] = None):
        """Make PUT request with Client-ID authorization"""
        headers = self.__generate_header(auth_type, required_scope)
        if data is None:
            return requests.put(url, headers=headers)
        else:
            return requests.put(url, headers=headers, json=data)

    def __api_get_request(self, url: str,
                          auth_type: 'AuthType',
                          required_scope: List[AuthScope]):
        """Make GET request with Client-ID authorization"""
        headers = self.__generate_header(auth_type, required_scope)
        return requests.get(url, headers=headers)

    def __generate_app_token(self):
        params = {
            'client_id': self.app_id,
            'client_secret': self.app_secret,
            'grant_type': 'client_credentials',
            'scope': build_scope(self.__app_auth_scope)
        }
        url = build_url(TWITCH_AUTH_BASE_URL + 'oauth2/token', params)
        result = requests.post(url)
        if result.status_code != 200:
            raise Exception(f'Authentication failed with code {result.status_code} ({result.text})')
        try:
            data = result.json()
            self.__app_auth_token = data['access_token']
        except ValueError:
            raise Exception('Authentication response did not have a valid json body')
        except KeyError:
            raise Exception('Authentication response did not contain access_token')

    def authenticate_app(self, scope: List[AuthScope]):
        self.__app_auth_scope = scope
        self.__generate_app_token()
        self.__has_app_auth = True

    def set_user_authentication(self, token: str, scope: List[AuthScope]):
        self.__user_auth_token = token
        self.__user_auth_scope = scope
        self.__has_user_auth = True

    def get_webhook(self, url: str, port: int) -> 'TwitchWebHook':
        """Returns a instance of TwitchWebHook"""
        return TwitchWebHook(url,
                             self.app_id,
                             port)

    def get_webhook_subscriptions(self, first: Union[str, None] = None, after: Union[str, None] = None):
        url = build_url(TWITCH_API_BASE_URL + 'webhooks/subscriptions',
                        {'first': first, 'after': after},
                        remove_none=True)
        response = self.__api_get_request(url, AuthType.APP)
        return response.json()

    def get_extension_analytics(self,
                                after: Union[str, None] = None,
                                extension_id: Union[str, None] = None,
                                first: int = 20,
                                ended_at: Union[datetime, None] = None,
                                started_at: Union[datetime, None] = None,
                                report_type: Union[AnalyticsReportType, None] = None):
        if ended_at is not None or started_at is not None:
            # you have to put in both:
            if ended_at is None or started_at is None:
                raise Exception('you must specify both ended_at and started_at')
            if started_at > ended_at:
                raise Exception('started_at must be before ended_at')
        if first > 100 or first < 1:
            raise Exception('first must be between 1 and 100')
        url_params = {
            'after': after,
            'ended_at': ended_at.isoformat() if ended_at is not None else None,
            'extension_id': extension_id,
            'first': first,
            'started_at': started_at.isoformat() if started_at is not None else None,
            'type': report_type.value if report_type is not None else None
        }
        url = build_url(TWITCH_API_BASE_URL + 'analytics/extensions',
                        url_params,
                        remove_none=True)
        response = self.__api_get_request(url, AuthType.USER, required_scope=[AuthScope.ANALYTICS_READ_EXTENSION])
        data = response.json()
        return make_fields_datetime(data, ['started_at', 'ended_at'])

    def get_game_analytics(self,
                           after: Union[str, None] = None,
                           first: int = 20,
                           game_id: Union[str, None] = None,
                           ended_at: Union[datetime, None] = None,
                           started_at: Union[datetime, None] = None,
                           report_type: Union[AnalyticsReportType, None] = None):
        if ended_at is not None or started_at is not None:
            if ended_at is None or started_at is None:
                raise Exception('you must specify both ended_at and started_at')
            if ended_at < started_at:
                raise Exception('ended_at must be after started_at')
        if first > 100 or first < 1:
            raise Exception('first must be between 1 and 100')
        url_params = {
            'after': after,
            'ended_at': ended_at.isoformat() if ended_at is not None else None,
            'first': first,
            'game_id': game_id,
            'started_at': started_at.isoformat() if started_at is not None else None,
            'type': report_type.value if report_type is not None else None
        }
        url = build_url(TWITCH_API_BASE_URL + 'analytics/games',
                        url_params,
                        remove_none=True)
        response = self.__api_get_request(url, AuthType.USER, [AuthScope.ANALYTICS_READ_GAMES])
        data = response.json()
        return make_fields_datetime(data, ['ended_at', 'started_at'])

    def get_bits_leaderboard(self,
                             count: int = 10,
                             period: TimePeriod = TimePeriod.ALL,
                             started_at: Union[datetime, None] = None,
                             user_id: Union[str, None] = None):
        if count > 100 or count < 1:
            raise Exception('count must be between 1 and 100')
        url_params = {
            'count': count,
            'period': period.value,
            'started_at': started_at.isoformat() if started_at is not None else None,
            'user_id': user_id
        }
        url = build_url(TWITCH_API_BASE_URL + 'bits/leaderboard', url_params, remove_none=True)
        response = self.__api_get_request(url, AuthType.USER, [AuthScope.BITS_READ])
        data = response.json()
        return make_fields_datetime(data, ['ended_at', 'started_at'])

    def get_extension_transactions(self,
                                   extension_id: str,
                                   transaction_id: Union[str, None] = None,
                                   after: Union[str, None] = None,
                                   first: int = 20):
        if first > 100 or first < 1:
            raise Exception("first must be between 1 and 100")
        url_param = {
            'extension_id': extension_id,
            'id': transaction_id,
            'after': after,
            first: first
        }
        url = build_url(TWITCH_API_BASE_URL + 'extensions/transactions', url_param, remove_none=True)
        result = self.__api_get_request(url, AuthType.APP, [])
        data = result.json()
        return make_fields_datetime(data, ['timestamp'])

    def create_clip(self,
                    broadcaster_id: str,
                    has_delay: bool = False):
        param = {
            'broadcaster_id': broadcaster_id,
            'has_delay': str(has_delay).lower()
        }
        url = build_url(TWITCH_API_BASE_URL + 'clips', param)
        result = self.__api_post_request(url, AuthType.USER, [AuthScope.CLIPS_EDIT])
        return result.json()

    def get_clips(self,
                  broadcaster_id: str,
                  game_id: str,
                  clip_id: List[str],
                  after: Union[str, None] = None,
                  before: Union[str, None] = None,
                  ended_at: Union[datetime, None] = None,
                  started_at: Union[datetime, None] = None):
        param = {
            'broadcaster_id': broadcaster_id,
            'game_id': game_id,
            'clip_id': clip_id,
            'after': after,
            'before': before,
            'ended_at': ended_at.isoformat() if ended_at is not None else None,
            'started_at': started_at.isoformat() if started_at is not None else None
        }
        url = build_url(TWITCH_API_BASE_URL + 'clips', param, split_lists=True, remove_none=True)
        result = self.__api_get_request(url, AuthType.NONE, [])
        data = result.json()
        return make_fields_datetime(data, ['created_at'])

    def create_entitlement_grants_upload_url(self,
                                             manifest_id: str):
        if len(manifest_id) < 1 or len(manifest_id) > 64:
            raise Exception('manifest_id must be between 1 and 64 characters long!')
        param = {
            'manifest_id': manifest_id,
            'type': 'bulk_drops_grant'
        }
        url = build_url(TWITCH_API_BASE_URL + 'entitlements/upload', param)
        result = self.__api_post_request(url, AuthType.APP, [])
        return result.json()

    def get_code_status(self,
                        code: List[str],
                        user_id: int):
        if code.count() > 20 or code.count() < 1:
            raise Exception('only between 1 and 20 codes are allowed')
        param = {
            'code': code,
            'user_id': user_id
        }
        url = build_url(TWITCH_API_BASE_URL + 'entitlements/codes', param, split_lists=True)
        result = self.__api_get_request(url, AuthType.APP, [])
        data = result.json()
        return fields_to_enum(data, ['status'], CodeStatus, CodeStatus.UNKNOWN_VALUE)

    def redeem_code(self,
                    code: List[str],
                    user_id: int):
        if code.count() > 20 or code.count() < 1:
            raise Exception('only between 1 and 20 codes are allowed')
        param = {
            'code': code,
            'user_id': user_id
        }
        url = build_url(TWITCH_API_BASE_URL + 'entitlements/code', param, split_lists=True)
        result = self.__api_post_request(url, AuthType.APP, [])
        data = result.json()
        return fields_to_enum(data, ['status'], CodeStatus, CodeStatus.UNKNOWN_VALUE)

    def get_top_games(self,
                      after: Optional[str] = None,
                      before: Optional[str] = None,
                      first: int = 20):
        if first < 1 or first > 100:
            raise Exception('first must be between 1 and 100')
        param = {
            'after': after,
            'before': before,
            'first': first
        }
        url = build_url(TWITCH_API_BASE_URL + 'games/top', param, remove_none=True)
        result = self.__api_get_request(url, AuthType.NONE, [])
        return result.json()

    def get_games(self,
                  game_ids: Optional[List[str]] = None,
                  names: Optional[List[str]] = None):
        if game_ids is None and names is None:
            raise Exception('at least one of either game_ids and names has to be set')
        if (len(game_ids) if game_ids is not None else 0) + (len(names) if names is not None else 0) > 100:
            raise Exception('in total, only 100 game_ids and names can be passed')
        param = {
            'id': game_ids,
            'name': names
        }
        url = build_url(TWITCH_API_BASE_URL + 'games', param, remove_none=True, split_lists=True)
        result = self.__api_get_request(url, AuthType.NONE, [])
        return result.json()

    def check_automod_status(self,
                             broadcaster_id: str,
                             msg_id: str,
                             msg_text: str,
                             user_id: str):
        # TODO you can pass multiple sets in the body, account for that
        url_param = {
            'broadcaster_id': broadcaster_id
        }
        url = build_url(TWITCH_API_BASE_URL + 'moderation/enforcements/status', url_param)
        body = {
            'data': [{
                'msg_id': msg_id,
                'msg_text': msg_text,
                'user_id': user_id}
            ]
        }
        result = self.__api_post_request(url, AuthType.USER, [AuthScope.MODERATION_READ], data=body)
        return result.json()

    def get_banned_events(self,
                          broadcaster_id: str,
                          user_id: Optional[str] = None,
                          after: Optional[str] = None,
                          first: int = 20):
        if first > 100 or first < 1:
            raise Exception('first must be between 1 and 100')
        param = {
            'broadcaster_id': broadcaster_id,
            'user_id': user_id,
            'after': after,
            'first': first
        }
        url = build_url(TWITCH_API_BASE_URL + 'moderation/banned/events', param, remove_none=True)
        result = self.__api_get_request(url, AuthType.USER, [AuthScope.MODERATION_READ])
        data = result.json()
        data = fields_to_enum(data, ['event_type'], ModerationEventType, ModerationEventType.UNKNOWN)
        data = make_fields_datetime(data, ['event_timestamp', 'expires_at'])
        return data

    def get_banned_users(self,
                         broadcaster_id: str,
                         user_id: Optional[str] = None,
                         after: Optional[str] = None,
                         before: Optional[str] = None):
        param = {
            'broadcaster_id': broadcaster_id,
            'user_id': user_id,
            'after': after,
            'before': before
        }
        url = build_url(TWITCH_API_BASE_URL + 'moderation/banned', param, remove_none=True)
        result = self.__api_get_request(url, AuthType.USER, [AuthScope.MODERATION_READ])
        return make_fields_datetime(result.json(), ['expires_at'])

    def get_moderators(self,
                       broadcaster_id: str,
                       user_id: Optional[str] = None,
                       after: Optional[str] = None):
        param = {
            'broadcaster_id': broadcaster_id,
            'user_id': user_id,
            'after': after
        }
        url = build_url(TWITCH_API_BASE_URL + 'moderation/moderators', param, remove_none=True)
        result = self.__api_get_request(url, AuthType.USER, [AuthScope.MODERATION_READ])
        return result.json()

    def get_moderator_events(self,
                             broadcaster_id: str,
                             user_id: Optional[str] = None):
        param = {
            'broadcaster_id': broadcaster_id,
            'user_id': user_id
        }
        url = build_url(TWITCH_API_BASE_URL + 'moderation/moderators/events', param, remove_none=True)
        result = self.__api_get_request(url, AuthType.USER, [AuthScope.MODERATION_READ])
        data = result.json()
        data = fields_to_enum(data, ['event_type'], ModerationEventType, ModerationEventType.UNKNOWN)
        data = make_fields_datetime(data, ['event_timestamp'])
        return data

    def create_stream_marker(self,
                             user_id: str,
                             description: Optional[str] = None):
        if description is not None and len(description) > 140:
            raise Exception('max length for description is 140')
        url = build_url(TWITCH_API_BASE_URL + 'streams/markers', {})
        body = {'user_id': user_id}
        if description is not None:
            body['description'] = description
        result = self.__api_post_request(url, AuthType.USER, [AuthScope.USER_EDIT_BROADCAST], data=body)
        data = result.json()
        return make_fields_datetime(data, ['created_at'])

    def get_streams(self,
                    after: Optional[str] = None,
                    before: Optional[str] = None,
                    first: int = 20,
                    game_id: Optional[str] = None,
                    language: Optional[List[str]] = None,
                    user_id: Optional[List[str]] = None,
                    user_login: Optional[List[str]] = None):
        if user_id is not None and len(user_id) > 100:
            raise Exception('a maximum of 100 user_ids are allowed')
        if user_login is not None and len(user_login) > 100:
            raise Exception('a maximum of 100 user_logins are allowed')
        if first > 100 or first < 1:
            raise Exception('first must be between 1 and 100')
        param = {
            'after': after,
            'before': before,
            'first': first,
            'game_id': game_id,
            'language': language,
            'user_id': user_id,
            'user_login': user_login
        }
        url = build_url(TWITCH_API_BASE_URL + 'streams', param, remove_none=True, split_lists=True)
        result = self.__api_get_request(url, AuthType.NONE, [])
        data = result.json()
        return make_fields_datetime(data, ['started_at'])

    def get_stream_markers(self,
                           user_id: str,
                           video_id: str,
                           after: Optional[str] = None,
                           before: Optional[str] = None,
                           first: int = 20):
        if first > 100 or first < 1:
            raise Exception('first must be between 1 and 100')
        param = {
            'user_id': user_id,
            'video_id': video_id,
            'after': after,
            'before': before,
            'first': first
        }
        url = build_url(TWITCH_API_BASE_URL + 'streams/markers', param, remove_none=True)
        result = self.__api_get_request(url, AuthType.USER, [AuthScope.USER_READ_BROADCAST])
        return make_fields_datetime(result.json(), ['created_at'])

    def get_streams_metadata(self,
                             after: Optional[str] = None,
                             before: Optional[str] = None,
                             first: int = 20,
                             game_id: Optional[List[str]] = None,
                             language: Optional[List[str]] = None,
                             user_id: Optional[List[str]] = None,
                             user_login: Optional[List[str]] = None):
        if first < 1 or first > 100:
            raise Exception('first must be between 1 and 100')
        if game_id is not None and len(game_id) > 100:
            raise Exception('game_id can have a maximum of 100 entries')
        if language is not None and len(language) > 100:
            raise Exception('language can have a maximum of 100 entries')
        if user_id is not None and len(user_id) > 100:
            raise Exception('user_id can have a maximum of 100 entries')
        if user_login is not None and len(user_login) > 100:
            raise Exception('user_login can have a maximum of 100 entries')
        param = {
            'after': after,
            'before': before,
            'first': first,
            'game_id': game_id,
            'language': language,
            'user_id': user_id,
            'user_login': user_login
        }
        url = build_url(TWITCH_API_BASE_URL + 'streams/metadata', param, remove_none=True, split_lists=True)
        result = self.__api_get_request(url, AuthType.NONE, [])
        return result.json()

    def get_broadcaster_subscriptions(self,
                                      broadcaster_id: str,
                                      user_ids: Optional[List[str]] = None):
        if user_ids is not None and len(user_ids) > 100:
            raise Exception('user_ids can have a maximum of 100 entries')
        param = {
            'broadcaster_id': broadcaster_id,
            'user_id': user_ids
        }
        url = build_url(TWITCH_API_BASE_URL + 'subscriptions', param, remove_none=True, split_lists=True)
        result = self.__api_get_request(url, AuthType.USER, [AuthScope.CHANNEL_READ_SUBSCRIPTIONS])
        return result.json()

    def get_all_stream_tags(self,
                            after: Optional[str] = None,
                            first: int = 20,
                            tag_ids: Optional[List[str]] = None):
        if first < 1 or first > 100:
            raise Exception('first must be between 1 and 100')
        if tag_ids is not None and len(tag_ids) > 100:
            raise Exception('tag_ids can not have more than 100 entries')
        param = {
            'after': after,
            'first': first,
            'tag_id': tag_ids
        }
        url = build_url(TWITCH_API_BASE_URL + 'tags/streams', param, remove_none=True, split_lists=True)
        result = self.__api_get_request(url, AuthType.APP, [])
        return result.json()

    def get_stream_tags(self,
                        broadcaster_id: str):
        url = build_url(TWITCH_API_BASE_URL + 'streams/tags', {'broadcaster_id': broadcaster_id})
        result = self.__api_get_request(url, AuthType.APP, [])
        return result.json()

    def replace_stream_tags(self,
                            broadcaster_id: str,
                            tag_ids: List[str]):
        if len(tag_ids) > 100:
            raise Exception('tag_ids can not have more than 100 entries')
        url = build_url(TWITCH_API_BASE_URL + 'streams/tags', {'broadcaster_id': broadcaster_id})
        self.__api_put_request(url, AuthType.USER, [AuthScope.USER_EDIT_BROADCAST], data={'tag_ids': tag_ids})
        # this returns nothing
        return {}

    def get_users(self,
                  user_ids: Optional[List[str]] = None,
                  logins: Optional[List[str]] = None):
        if user_ids is None and logins is None:
            raise Exception('please either specify user_ids or logins')
        if (len(user_ids) if user_ids is not None else 0) + (len(logins) if logins is not None else 0) > 100:
            raise Exception('the total number of entries in user_ids and logins can not be more than 100')
        url_params = {
            'id': user_ids,
            'login': logins
        }
        url = build_url(TWITCH_API_BASE_URL + 'users', url_params, remove_none=True, split_lists=True)
        response = self.__api_get_request(url, AuthType.NONE, [])
        return response.json()

    def get_users_follows(self,
                          after: Optional[str] = None,
                          first: int = 20,
                          from_id: Optional[str] = None,
                          to_id: Optional[str] = None):
        if first > 100 or first < 1:
            raise Exception('first must be between 1 and 100')
        if from_id is None and to_id is None:
            raise Exception('at least one of from_id and to_id needs to be set')
        param = {
            'after': after,
            'first': first,
            'from_id': from_id,
            'to_id': to_id
        }
        url = build_url(TWITCH_API_BASE_URL + 'users/follows', param, remove_none=True)
        result = self.__api_get_request(url, AuthType.NONE, [])
        return make_fields_datetime(result.json(), ['followed_at'])