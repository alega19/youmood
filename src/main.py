import io
import itertools
import json
import logging
import os
import pathlib
import re
import signal
import socket
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import imageio.v3 as iio
import pytube
import pytube.exceptions
import rmn
import torch
import yoyo
from hsemotion.facial_emotions import HSEmotionRecognizer
from PIL import Image

import db
import logging_config
import pytube_patch
import utils


logger = logging.getLogger("youmood")

GOOGLE_API_KEY = os.environ["GOOGLE_API_KEY"]
PROCESSING_INTERVAL = timedelta(days=7)
SYNC_INTERVAL = timedelta(days=1)

pytube_patch.init()


def main():
    utils.start_thread(synchronize_channels)
    while True:
        video = get_video()
        if video:
            try:
                results, video = analyze_video(video)
            except Exception as error:
                logger.error("error when analyzing video(%s) %s: %s", video["id"], video["title"] or "", error, exc_info=not isinstance(error, utils.Error))
                set_video_stage(video["id"], -ProcessingStage.ANALYZED)
            else:
                set_video_stage(video["id"], ProcessingStage.ANALYZED)
                save(video, results)


def migrate():
    backend = yoyo.get_backend(db.DSN)
    migrations = yoyo.read_migrations(str(pathlib.Path(__file__).parent / "migrations"))
    with backend.lock():
        backend.apply_migrations(backend.to_apply(migrations))


@utils.retry(60, repeat_last=True)
def synchronize_channels():
    while True:
        channel_ids = select_channels()
        for channel_id in channel_ids:
            try:
                synchronize_channel(channel_id)
            except Exception as error:
                logger.exception("error: %s", error)


def get_video():
    video = select_video()
    if video:
        try:
            video = download_video(video)
        except Exception as error:
            logger.error("error when downloading video(%s) %s: %s", video["id"], video["title"] or "", error, exc_info=not isinstance(error, utils.Error))
            set_video_stage(video["id"], -ProcessingStage.DOWNLOADED)
        else:
            set_video_stage(video["id"], ProcessingStage.DOWNLOADED)
            return video
    return None


def analyze_video(video):
    label_to_max_score = defaultdict(float)
    face_detector = RMN()
    analyzer = HSEmotionRecognizer()
    results = []
    logger.info("fps: %s", video["fps"])
    frames = iio.imiter(video["buffer"], extension=".mp4")
    frame = next(frames)
    if frame.shape[0] > frame.shape[1]:
        raise utils.Error("it seems to be short")
    frame_index = 0
    for frame in itertools.chain([frame], frames):
        if frame_index % video["fps"] == 0:
            seconds = frame_index // video["fps"]
            if seconds % 60 == 0:
                logger.info("processed %s minutes for video(%s)", seconds // 60, video["id"])
            face_image = face_detector.find_face(frame)
            if face_image is not None:
                label, scores = analyzer.predict_emotions(face_image, False)
                score = scores.max().item()
                if score >= label_to_max_score[label]:
                    label_to_max_score[label] = score
                    save_face(video["channel_id"], label, face_image)
                results.append(label)
        frame_index += 1
    logger.info("analyzed video(%s): %s", video["id"], video["title"])
    return results, {**video, "num_frames": frame_index + 1}


@utils.retry(1, 3, 10, 30, 60)
@db.use
def save(video, results, *, db_connection):
    video_id = video["id"]
    label_to_num_frames = defaultdict(int)
    if results:
        for label in results:
            label_to_num_frames[label] += 1
        with db_connection.transaction():
            db_connection.execute(
                """
                UPDATE "video" SET
                "fps"=%s, "num_frames"=%s,
                "angry"=%s, "disgust"=%s, "fear"=%s, "happy"=%s, "neutral"=%s, "sad"=%s, "surprise"=%s, "contempt"=%s
                WHERE "id" = %s
                """,
                (
                    video["fps"],
                    video["num_frames"],
                    label_to_num_frames["Anger"],
                    label_to_num_frames["Disgust"],
                    label_to_num_frames["Fear"],
                    label_to_num_frames["Happiness"],
                    label_to_num_frames["Neutral"],
                    label_to_num_frames["Sadness"],
                    label_to_num_frames["Surprise"],
                    label_to_num_frames["Contempt"],
                    video_id
                ),
            )
            set_video_stage(video_id, ProcessingStage.SAVED, db_connection=db_connection)
        update_channel(video["channel_id"], db_connection=db_connection)
        logger.info("saved data for video(%s)", video_id)
    else:
        set_video_stage(video_id, -ProcessingStage.SAVED, db_connection=db_connection)


@utils.retry(1, 3, 10, 30, 60, repeat_last=True)
@utils.rate_limit(bucket_time=60)
@db.use
def select_channels(*, db_connection):
    query = """
        WITH "last_processed_video" AS (
            SELECT DISTINCT ON ("channel_id") "channel_id", "published"
            FROM "video"
            WHERE "stage" = %s
            ORDER BY "channel_id", "published" DESC
        )
        SELECT "channel"."id"
        FROM "channel"
        LEFT JOIN "last_processed_video" ON "last_processed_video"."channel_id" = "channel"."id"
        WHERE coalesce("last_processed_video"."published", '1970-01-01T00:00Z'::timestamptz) < %s
          AND coalesce("channel"."synchronized", '1970-01-01T00:00Z'::timestamptz) < %s
        ORDER BY "channel"."synchronized" NULLS FIRST, "channel"."id"
    """
    now = utils.now()
    rows = db_connection.fetch(query, (ProcessingStage.SAVED, now - PROCESSING_INTERVAL, now - SYNC_INTERVAL))
    logger.info("selected %s channels to synchronize", len(rows))
    return [channel_id for channel_id, in rows]


@utils.cached(SYNC_INTERVAL.total_seconds())
@utils.retry(1, 3, 10, 30, 60)
@utils.rate_limit(bucket_time=timedelta(hours=24).total_seconds(), bucket_size=110)
@utils.rate_limit(bucket_time=60)
@db.use
def synchronize_channel(
    channel_id,
    url_pattern="https://youtube.googleapis.com/youtube/v3/search?part=snippet&channelId={0}&maxResults={1}&order=date&type=video",
    num_video_max=50,
    *,
    db_connection,
):
    url = url_pattern.format(channel_id, num_video_max)
    request = urllib.request.Request(url, headers={"X-goog-api-key": GOOGLE_API_KEY})
    response = urllib.request.urlopen(request)
    utils.Error.assert_(response.status == 200, f"expected status 200 instead of {response.status}")
    data = response.read()
    result = json.loads(data)

    now = utils.now()
    channel_title = None
    params_list = []
    for item in result["items"]:
        snippet = item["snippet"]
        if snippet["channelId"] == channel_id:
            channel_title = channel_title or snippet.get("channelTitle")
            video_id = item["id"]["videoId"]
            published = datetime.strptime(snippet["publishedAt"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            params_list.append((video_id, channel_id, now, published, snippet.get("title")))
    with db_connection.transaction():
        query = """UPDATE "channel" SET "title" = coalesce(%s, "title"), "synchronized" = %s WHERE "id" = %s"""
        db_connection.execute(query, (channel_title, now, channel_id))
        if params_list:
            query = """
                INSERT INTO "video" ("id", "channel_id", "found", "published", "title") VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """
            db_connection.executemany(query, params_list)
    logger.info("synchronized channel(%s): %s", channel_id, channel_title or "")


@utils.retry(1, 3, 10, 30, 60, repeat_last=True)
@utils.rate_limit(bucket_time=5)
@db.use
def select_video(video_age_max=timedelta(days=30), *, db_connection):
    query = """
        WITH "last_video" AS (
            SELECT DISTINCT ON ("channel_id") "channel_id", "id", "published", "title"
            FROM "video"
            WHERE "stage" >= 0 AND "stage" <> %s
            ORDER BY "channel_id", "published" DESC
        ),
        "last_processed_video" AS (
            SELECT DISTINCT ON ("channel_id") "channel_id", "id", "published"
            FROM "video"
            WHERE "stage" = %s
            ORDER BY "channel_id", "published" DESC
        )
        SELECT "last_video"."id", "last_video"."title", "last_video"."channel_id"
        FROM "last_video"
        LEFT JOIN "last_processed_video" ON "last_processed_video"."channel_id" = "last_video"."channel_id"
        WHERE %s < "last_video"."published"
          AND coalesce("last_processed_video"."published", '1970-01-01T00:00Z'::timestamptz) < %s
        ORDER BY "last_processed_video"."published" NULLS FIRST
        LIMIT 1
    """
    now = utils.now()
    params = (ProcessingStage.SAVED, ProcessingStage.SAVED, now - video_age_max, now - PROCESSING_INTERVAL)
    try:
        id_, title, channel_id = db_connection.fetchrow(query, params)
    except db.EmptyResult:
        return None
    else:
        logger.info("selected video(%s): %s", id_, title or "")
        return {"id": id_, "title": title, "channel_id": channel_id}


@utils.retry(1, 3, 10, 30, 60, bypass=(pytube.exceptions.VideoUnavailable,))
@utils.rate_limit(bucket_time=5)
def download_video(video, url_pattern="https://www.youtube.com/watch?v={}"):

    def check_is_not_short(_, chunk, __):
        try:
            frame = iio.imread(chunk, index=0, extension=".mp4")
        except Exception:
            pass
        else:
            if frame.shape[0] > frame.shape[1]:
                raise utils.NoRetry("it seems to be short")

    url = url_pattern.format(video["id"])
    yt = pytube.YouTube(url, on_progress_callback=check_is_not_short, use_oauth=True, allow_oauth_cache=True)
    streams = yt.streams.filter(type="video", subtype="mp4").order_by("resolution")
    try:
        stream = next(allowed_streams(streams))
    except StopIteration:
        raise utils.Error("no suitable stream")
    else:
        buffer = io.BytesIO()
        stream.stream_to_buffer(buffer)
        logger.info("downloaded video(%s): %s", video["id"], video["title"] or "")
        buffer.seek(0)
        return {**video, "fps": stream.fps, "buffer": buffer}


@utils.retry(1, 3, 10, 30, 60, repeat_last=True)
@db.use
def set_video_stage(video_id, stage, *, db_connection):
    query = """UPDATE "video" SET "stage" = %s WHERE "id" = %s"""
    db_connection.execute(query, (stage, video_id))


@utils.retry(1, 3, 10, 30, 60, repeat_last=True)
@db.use
def update_channel(channel_id, *, db_connection):
    rows = db_connection.fetch(
        """
        SELECT
            sum("angry")::real / sum("num_frames"::real/"fps"),
            sum("happy")::real / sum("num_frames"::real/"fps"),
            sum("sad")::real / sum("num_frames"::real/"fps"),
            sum("surprise")::real / sum("num_frames"::real/"fps"),
            sum("fear")::real / sum("num_frames"::real/"fps"),
            sum("disgust")::real / sum("num_frames"::real/"fps"),
            sum("neutral")::real / sum("num_frames"::real/"fps"),
            sum("contempt")::real / sum("num_frames"::real/"fps")
        FROM "video"
        WHERE "channel_id" = %s AND "published" > %s AND "num_frames" IS NOT NULL AND "fps" IS NOT NULL
            AND "angry" IS NOT NULL AND "happy" IS NOT NULL AND "sad" IS NOT NULL AND "surprise" IS NOT NULL
            AND "fear" IS NOT NULL AND "disgust" IS NOT NULL AND "neutral" IS NOT NULL AND "contempt" IS NOT NULL
        """,
        (channel_id, utils.now() - timedelta(days=30)),
    )
    if rows:
        db_connection.execute(
            """
            UPDATE "channel" SET
            "angry"=%s, "happy"=%s, "sad"=%s, "surprise"=%s, "fear"=%s, "disgust"=%s, "neutral"=%s, "contempt"=%s
            WHERE "id"=%s
            """,
            (*rows[0], channel_id),
        )
        logger.info("updated channel %s", channel_id)


def allowed_streams(streams, res_regexp=re.compile("([0-9]+)")):
    for stream in streams:
        if stream.fps and 20 <= stream.fps <= 30:
            match = res_regexp.match(stream.resolution)
            if match and 480 <= int(match[1]) <= 720:
                yield stream


class ProcessingStage:
    NONE = 0
    DOWNLOADED = 1
    ANALYZED = 2
    SAVED = 3


class RMN(rmn.RMN):
    @torch.no_grad()
    def find_face(self, frame):
        face_results = self.detect_faces(frame)
        if face_results:
            face = max(face_results, key=lambda f: (f["xmax"] - f["xmin"]) * (f["ymax"] - f["ymin"]))
            face_image = frame[face["ymin"]:face["ymax"], face["xmin"]:face["xmax"]]
            if min(face_image.shape[:2]) >= 10:
                return face_image
        return None


def save_face(channel_id, label, image):
    column = db.LABEL_TO_COLUMN[label]
    filepath = pathlib.Path(__file__).parent / "images" / channel_id / (column + ".jpg")
    filepath.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image).save(filepath)
    logger.info("saved %s face for channel-id=%s", label, channel_id)


if __name__ == '__main__':
    logging_config.apply()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit())
    logger.info("started")
    socket.setdefaulttimeout(600)
    db.register_dict_as_json()
    try:
        migrate()
        main()
    except Exception as _error:
        logger.exception("unexpected error: %s", _error)
        sys.exit(1)
    finally:
        logger.info("stopped")
