from typing import Optional, Any, cast
from mautrix.client import ClientAPI
import PIL.ImageOps
from io import BytesIO
import PIL.Image
from PIL.Image import Image
from mautrix.types import MediaMessageEventContent, MessageType, EventID, ContentURI, TextMessageEventContent
from maubot import Plugin, MessageEvent
from maubot.handlers import command
import warnings
from .parameters import BASELINE, DURATION, SQUISHINESS
import re

MATRIX_TO_REGEX = re.compile("""https?:\/\/matrix.to\/#\/(@[A-Za-z0-9_]+:[A-Za-z0-9_.]+)""")

warnings.simplefilter("error", PIL.Image.DecompressionBombWarning)

class PetBot(Plugin):
    async def start(self):
        self.frames: list[Image] = []
        frames_list = await self.loader.list_files("frames")

        for frame_path in sorted(frames_list):
            frame_bytes = await self.loader.read_file(frame_path)
            image = PIL.Image.open(BytesIO(frame_bytes)).convert("RGBA")
            self.frames.append(image)

    async def stop(self):
        for frame in self.frames:
            frame.close()

        self.frames = []

    def create_petpet(self, image: Image) -> BytesIO:
        image = image.convert("RGBA")
        target_width, target_height = self.frames[0].size
        fitted = PIL.ImageOps.fit(image, (target_width, target_height))

        result_frames = []

        for i, petpet_frame in enumerate(self.frames):
            next_frame = PIL.Image.new("RGBA", (target_width, target_height))

            t = i / len(self.frames)
            if t >= .5:
                t = 1 - t
            
            t *= 2

            squish = t * (1 - SQUISHINESS)
            squished_height = round(target_height * (1 - squish) * BASELINE)
            squish_y = target_height - squished_height

            squished = fitted.resize(
                (target_width, squished_height),
                PIL.Image.Resampling.LANCZOS,
            )

            next_frame.paste(squished, (0, squish_y))
            next_frame.alpha_composite(petpet_frame)
            result_frames.append(next_frame)

        result = BytesIO()
        result_frames[0].save(
            result,
            format="gif",
            save_all=True,
            append_images=result_frames[1:],
            duration=DURATION,
            loop=0,
            disposal=2
        )
        
        result.seek(0)
        return result

    async def petpet_from_url(self, evt: MessageEvent, url: ContentURI) -> None:
        image_bytes = await self.client.download_media(url)
        try:
            with BytesIO(image_bytes) as io:
                image = PIL.Image.open(io)
                image.load()
        except Exception as e:
            self.log.exception(e)
            await evt.reply("Failed to load media")
            return

        try:
            with self.create_petpet(image) as out_io:
                uploading_bytes = out_io.read()
                if len(uploading_bytes) <= 0:
                    self.log.error("Trying to upload an empty image")
                    await evt.reply("Internal error occurred")
                    return

                mxc = await self.client.upload_media(uploading_bytes, mime_type="image/gif", filename="petpet.gif")
                await self.client.send_image(room_id=evt.room_id, url=mxc, file_name="petpet.gif")

        except Exception as e:
            self.log.exception(e)
            await evt.reply("Failed to create petpet")

    async def petpet_reply(self, evt: MessageEvent, reply_event_id: EventID) -> None:
        reply_event = await self.client.get_event(evt.room_id, reply_event_id)

        if not isinstance(reply_event, MessageEvent):
            await evt.reply("Reply to a message, not any other event!")
            return

        if not isinstance(reply_event.content, MediaMessageEventContent):
            await evt.respond("The replied to message must contain media!")
            return

        content = reply_event.content

        if content.msgtype != MessageType.IMAGE:
            await evt.reply("The replied to message had unexpected non-image media!")
            return

        if not content.url:
            await evt.reply("URLless media, how is this possible?")
            return

        await self.petpet_from_url(evt, content.url)

    async def petpet_user(self, evt: MessageEvent, user: str):
        avatar_url = await self.client.get_avatar_url(user)

        if avatar_url is None:
            await evt.reply("User does not have an avatar!")
            return

        await self.petpet_from_url(evt, avatar_url)

    @command.new()  # ty:ignore[call-non-callable]
    @command.argument("user", required=False)
    async def petpet(self, evt: MessageEvent, user: str | None) -> None:
        mentions: dict[str, Any] = evt.content.get("m.mentions", dict())
        user_ids: list[str] = mentions.get('user_ids', [])

        if user is not None:
            if len(user_ids) > 0:
                await self.petpet_user(evt, user_ids[0])
                return

            try:
                ClientAPI.parse_user_id(user)
                await self.petpet_user(evt, user)
            except ValueError:
                pass

            matches = MATRIX_TO_REGEX.findall(cast(TextMessageEventContent, evt.content).formatted_body)
            if len(matches) == 0:
                await evt.reply("Sorry, that does not look like a valid user!")
                return

            await self.petpet_user(evt, matches[0])

            return

        reply_event_id = evt.content.get_reply_to()
        if reply_event_id:
            await self.petpet_reply(evt, reply_event_id)
            return

        await evt.reply("Either reply to media, or mention a users' mxid!")

        

        
