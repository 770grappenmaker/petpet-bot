from io import BytesIO
import PIL.Image
from PIL.Image import Image
from mautrix.types import MediaMessageEventContent, MessageType
from maubot import Plugin, MessageEvent
from maubot.handlers import command
import warnings

warnings.simplefilter("error", PIL.Image.DecompressionBombWarning)


class PetBot(Plugin):
    frames: list[Image] = []

    async def start(self):
        frames_list = await self.loader.list_files("frames")

        for frame_path in sorted(frames_list):
            frame_bytes = await self.loader.read_file(frame_path)
            image = PIL.Image.open(BytesIO(frame_bytes))
            self.frames.append(image)

    async def stop(self):
        for frame in self.frames:
            frame.close()

        self.frames = []

    async def create_petpet(self, image: Image) -> BytesIO:
        copies = [frame.copy() for frame in self.frames]
        result = BytesIO()
        copies[0].save(
            result,
            format="gif",
            save_all=True,
            append_images=copies[1:],
            duration=100,
            loop=0,
        )
        
        return result

    @command.new()  # ty:ignore[call-non-callable]
    async def petpet(self, evt: MessageEvent) -> None:
        reply_event_id = evt.content.get_reply_to()
        if not reply_event_id:
            await evt.reply("Reply to an image!")
            return

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

        image_bytes = await self.client.download_media(content.url)
        try:
            with BytesIO(image_bytes) as io:
                image = PIL.Image.open(io)
                image.load()
        except:
            await evt.reply("Failed to load media")
            return

        try:
            with await self.create_petpet(image) as out_io:
                mxc = await self.client.upload_media(out_io.read(), mime_type="image/png", filename="petpet.png")
                await self.client.send_image(room_id=evt.room_id, url=mxc, file_name="petpet.png")
        except:
            await evt.reply("Failed to create petpet")
            return
