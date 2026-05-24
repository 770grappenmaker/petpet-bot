import PIL.ImageOps
from io import BytesIO
import PIL.Image
from PIL.Image import Image
from mautrix.types import MediaMessageEventContent, MessageType
from maubot import Plugin, MessageEvent
from maubot.handlers import command
import warnings

warnings.simplefilter("error", PIL.Image.DecompressionBombWarning)

SQUISHINESS = .7
DURATION = 25

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
            squished_height = round(target_height * (1 - squish))
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
            return
