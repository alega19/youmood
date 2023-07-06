CREATE TABLE "video" (
    "id" text NOT NULL,
    "channel_id" text NOT NULL,
    "found" timestamptz NOT NULL,
    "published" timestamptz NOT NULL,
    "title" text,
    "stage" int2 NOT NULL DEFAULT 0,
    "fps" int2,
    "num_frames" int4,

    "angry" int8,
    "happy" int8,
    "sad" int8,
    "surprise" int8,
    "fear" int8,
    "disgust" int8,
    "neutral" int8,
    "contempt" int8,

    CONSTRAINT "video_pk" PRIMARY KEY ("id"),
    CONSTRAINT "video_id_non_empty" CHECK (length("id") > 0),
    CONSTRAINT "video_fk_channel_id" FOREIGN KEY ("channel_id") REFERENCES "channel" ("id")
);

CREATE INDEX "video_channel_id_published_index" ON "video" ("channel_id", "published");
