import asyncio
import logging
import random
from typing import Dict, Optional

import emoji
import hangups


class HangoutsBot:
    _token_path: str
    _client: hangups.Client
    _conv_list: hangups.ConversationList
    _user_list: hangups.UserList

    def __init__(self, token_path: str) -> None:
        self._token_path = token_path
        self._client = None
        self._conv_list = None
        self._user_list = None

    def login(self, token_path: str) -> Optional[Dict]:
        try:
            cookies = hangups.auth.get_auth_stdin(token_path)
            return cookies
        except hangups.GoogleAuthError:
            logging.exception('Error while attempting to login')
            return None

    def run(self) -> None:
        cookies = self.login(self._token_path)
        self._client = hangups.Client(cookies)
        self._client.on_connect.add_observer(self._on_connect)
        loop = asyncio.get_event_loop()

        task = asyncio.ensure_future(self._client.connect())

        try:
            loop.run_until_complete(task)
        except KeyboardInterrupt:
            task.cancel()
            loop.run_until_complete(task)
        finally:
            loop.close()

    def send_message(self, conv_id: str, message: str) -> None:
        self.send_message_segments(conv_id,
                                   [hangups.ChatMessageSegment(message)])

    def send_message_segments(self, conv_id: str, segments) -> None:
        conv = self._conv_list.get(conv_id)
        asyncio.ensure_future(conv.send_message(segments))

    async def _on_event(self, conv_event: hangups.ConversationEvent) -> None:
        sender = self._user_list.get_user(conv_event.user_id)
        if sender.is_self:
            return
        if isinstance(conv_event, hangups.ChatMessageEvent):
            await self._on_message(conv_event)

    async def _on_message(self, conv_event):
        conv_id = conv_event.conversation_id
        user = self._user_list.get_user(conv_event.user_id)
        print('{}: {!r}'.format(user.full_name, conv_event.text))

        if 'daniel' in conv_event.text.lower():
            await self._clone(conv_id)

        if 'emogi' in conv_event.text.lower():
            self.send_message(conv_id, emoji.random_emoji()[0])

        # if 'oppress' in conv_event.text.lower():
        #     for i in range(50):
        #         await self._set_otr_status(conv_event.conversation_id, (i % 2) + 1)

        #     self.send_message(conv_event.conversation_id,
        #                       hangups.ChatMessageSegment('okay'))

        # key = '!squadup'
        # if key in conv_event.text.lower():
        #     await self._purge(conv_id)

        # if 'daniel' in conv_event.text.lower():
        #     await self._kick_random(conv_id)

        # if conv_event.text == 'Hi Leo':
        #     for i in range(100):
        #         await self._conv_list.get(conv_event.conversation_id).rename("Hi gigolo " + str(i))
        # if conv_event.text == '!music':
        #     self.send_message(conv_id,
        #                       hangups.ChatMessageSegment('no'))

    async def _on_connect(self) -> None:
        print('connected')
        self._user_list, self._conv_list = (
            await hangups.build_user_conversation_list(self._client))
        self._conv_list.on_event.add_observer(self._on_event)
        self._print_convs()
        self._print_users()

    async def _add_user(self, conv_id: str, user_gaia_id: str) -> None:
        conv = self._conv_list.get(conv_id)
        request = hangups.hangouts_pb2.AddUserRequest(
            request_header=self._client.get_request_header(),
            event_request_header=conv._get_event_request_header(),
            invitee_id=hangups.hangouts_pb2.InviteeID(gaia_id=user_gaia_id, ))
        await self._client.add_user(request)

    async def _remove_user(self, conv_id: str, user_gaia_id: str) -> None:
        conv = self._conv_list.get(conv_id)
        request = hangups.hangouts_pb2.RemoveUserRequest(
            request_header=self._client.get_request_header(),
            event_request_header=conv._get_event_request_header(),
            participant_id=hangups.hangouts_pb2.ParticipantId(
                gaia_id=user_gaia_id),
        )
        await self._client.remove_user(request)

    async def _set_otr_status(self, conv_id: str, status: int) -> None:
        conv = self._conv_list.get(conv_id)
        request = hangups.hangouts_pb2.ModifyOTRStatusRequest(
            request_header=self._client.get_request_header(),
            event_request_header=conv._get_event_request_header(),
            otr_status=status)
        await self._client.modify_otr_status(request)

    async def _purge(self, conv_id: str) -> None:
        conv = self._conv_list.get(conv_id)
        for user in conv.users:
            if not user.is_self:
                await self._remove_user(conv_id, user.id_.gaia_id)
        await self._conv_list.leave_conversation(conv_id)

    async def _clone(self, conv_id: str) -> None:
        conv = self._conv_list.get(conv_id)
        ids = [
            hangups.hangouts_pb2.InviteeID(
                gaia_id=u.id_.gaia_id, fallback_name=u.full_name)
            for u in conv.users
        ]

        req = hangups.hangouts_pb2.CreateConversationRequest(
            request_header=self._client.get_request_header(),
            type=hangups.hangouts_pb2.CONVERSATION_TYPE_GROUP,
            client_generated_id=self._client.get_client_generated_id(),
            name=conv.name,
            invitee_id=ids)
        res = await self._client.create_conversation(req)
        self._conv_list._add_conversation(res.conversation)

        conv_id = res.conversation.conversation_id.id
        conv = self._conv_list.get(conv_id)
        self.send_message(conv_id, "Hi")

    async def _kick_random(self, conv_id: str) -> None:
        conv = self._conv_list.get(conv_id)
        user = random.choice(conv.users)
        while user.is_self:
            user = random.choice(conv.users)
        await self._remove_user(conv_id, user.id_.gaia_id)

    def _print_convs(self) -> None:
        conversations = self._conv_list.get_all(include_archived=True)
        print('{} known conversations'.format(len(conversations)))
        for conversation in conversations:
            if conversation.name:
                name = conversation.name
            else:
                name = 'Unnamed conversation ({})'.format(conversation.id_)
            print('    {}'.format(name))

    def _print_users(self) -> None:
        users = self._user_list.get_all()
        print('{} known users'.format(len(users)))
        for user in users:
            print('    {}'.format(user.full_name))